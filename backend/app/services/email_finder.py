"""
Multi-strategy email finder.

Strategy order:
  1. Hunter.io Domain Search API
  2. Emails already scraped from the website
  3. Name permutation + DNS MX / SMTP RCPT TO verification

Stops early when a verified result with confidence > 70 is found.
"""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import socket
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import dns.resolver
import httpx
import redis

from app.config import settings

logger = logging.getLogger(__name__)

# ── Redis for Hunter quota tracking ─────────────────────────────────────────

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None

HUNTER_MONTHLY_LIMIT = 25
HUNTER_BUFFER = 2  # start skipping when usage >= 23

# Major providers that block SMTP RCPT TO probing
MAJOR_PROVIDERS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
    "live.com", "yahoo.com", "yahoo.co.uk", "aol.com", "icloud.com",
    "me.com", "protonmail.com", "proton.me", "zoho.com",
})

# Generic prefixes to filter out from scraped emails
GENERIC_PREFIXES = frozenset({
    "info", "hello", "contact", "support", "admin", "noreply",
    "no-reply", "sales", "help", "webmaster", "postmaster",
    "office", "team", "billing", "enquiry", "enquiries",
})


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class ContactResult:
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    designation: Optional[str]
    email: str
    email_confidence: int       # 0-100
    email_status: str           # 'verified', 'unverified', 'invalid'
    source: str                 # 'hunter', 'scraped', 'permutation'

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
#  EmailFinder
# ═══════════════════════════════════════════════════════════════════════════


class EmailFinder:
    """Orchestrates all three email-finding strategies."""

    # ── Public entry point ──────────────────────────────────────────────

    async def find_email(self, lead: dict) -> List[ContactResult]:
        """
        Run strategies in order for a lead. Stop early when a verified
        result with confidence > 70 is found.

        Parameters
        ----------
        lead : dict
            Must include at minimum ``website``.  May also include
            ``raw_data`` (dict with ``email_addresses``, etc.).
        """
        domain = self._extract_domain(lead.get("website", ""))
        if not domain:
            logger.warning("No valid domain for lead %s — skipping", lead.get("id"))
            return []

        results: List[ContactResult] = []

        # ── Strategy 1: Hunter.io ───────────────────────────────────────
        if not self._hunter_quota_exhausted():
            hunter_results = await self._search_hunter(domain)
            results.extend(hunter_results)
            if self._has_verified(results):
                return results

        # ── Strategy 2: Scraped page emails ─────────────────────────────
        raw_data = lead.get("raw_data") or {}
        scraped_results = self._extract_from_page(raw_data)
        results.extend(scraped_results)
        if self._has_verified(results):
            return results

        # ── Strategy 3: Permutation + SMTP verification ─────────────────
        # Collect any name hints from Hunter partial data
        name_hints: list[str] = []
        for r in results:
            parts = [r.first_name, r.last_name]
            name = " ".join(p for p in parts if p).strip()
            if name:
                name_hints.append(name)

        perm_results = await self._permutate_and_verify(domain, name_hints or None)
        results.extend(perm_results)

        return results

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _has_verified(results: List[ContactResult]) -> bool:
        return any(
            r.email_status == "verified" and r.email_confidence > 70
            for r in results
        )

    # ═══════════════════════════════════════════════════════════════════
    #  Strategy 1 — Hunter.io Domain Search
    # ═══════════════════════════════════════════════════════════════════

    async def _search_hunter(self, domain: str) -> List[ContactResult]:
        """Query Hunter.io Domain Search and return mapped contacts."""
        api_key = settings.HUNTER_API_KEY
        if not api_key:
            logger.info("HUNTER_API_KEY not set — skipping Hunter strategy")
            return []

        url = "https://api.hunter.io/v2/domain-search"
        params = {
            "domain": domain,
            "api_key": api_key,
            "limit": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)

            if resp.status_code == 401:
                logger.error("Hunter.io: invalid API key")
                return []
            if resp.status_code == 429:
                logger.warning("Hunter.io: rate limited (429)")
                return []
            if resp.status_code == 422:
                logger.info("Hunter.io: invalid domain %s (422)", domain)
                return []

            resp.raise_for_status()
            data = resp.json().get("data", {})

            # Track usage
            self._increment_hunter_usage()

            # Log usage for debugging
            logger.info(
                "Hunter.io search for %s — returned %d emails",
                domain,
                len(data.get("emails", [])),
            )

            contacts: List[ContactResult] = []
            for entry in data.get("emails", []):
                confidence = entry.get("confidence", 0)
                contacts.append(ContactResult(
                    first_name=entry.get("first_name") or None,
                    last_name=entry.get("last_name") or None,
                    full_name=None,  # Hunter separates first/last
                    designation=entry.get("position") or None,
                    email=entry["value"],
                    email_confidence=confidence,
                    email_status="verified" if confidence > 70 else "unverified",
                    source="hunter",
                ))

            # Sort by confidence descending
            contacts.sort(key=lambda c: c.email_confidence, reverse=True)
            return contacts

        except httpx.HTTPStatusError as exc:
            logger.error("Hunter.io HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.error("Hunter.io unexpected error: %s", exc)
            return []

    # ── Hunter quota helpers ────────────────────────────────────────────

    @staticmethod
    def _hunter_quota_key() -> str:
        now = datetime.now(timezone.utc)
        return f"hunter:usage:month:{now.strftime('%Y-%m')}"

    def _hunter_quota_exhausted(self) -> bool:
        if not _redis:
            return False
        try:
            usage = int(_redis.get(self._hunter_quota_key()) or 0)
            return usage >= (HUNTER_MONTHLY_LIMIT - HUNTER_BUFFER)
        except Exception:
            return False

    def _increment_hunter_usage(self) -> None:
        if not _redis:
            return
        try:
            key = self._hunter_quota_key()
            pipe = _redis.pipeline()
            pipe.incr(key)
            # Expire at end of month + 2 days buffer
            pipe.expire(key, 33 * 24 * 3600)
            pipe.execute()
        except Exception as exc:
            logger.warning("Failed to increment Hunter usage counter: %s", exc)

    # ═══════════════════════════════════════════════════════════════════
    #  Strategy 2 — Emails from scraped page
    # ═══════════════════════════════════════════════════════════════════

    def _extract_from_page(self, raw_data: dict) -> List[ContactResult]:
        """
        Use emails already discovered by the scraper.
        Filters out generic prefixes (info@, hello@, etc.).
        """
        email_addresses: list = raw_data.get("email_addresses") or []
        if not email_addresses:
            return []

        contacts: List[ContactResult] = []
        for email in email_addresses:
            email = email.strip().lower()
            if not email or "@" not in email:
                continue

            prefix = email.split("@")[0]
            if prefix in GENERIC_PREFIXES:
                continue

            contacts.append(ContactResult(
                first_name=None,
                last_name=None,
                full_name=None,
                designation=None,
                email=email,
                email_confidence=60,
                email_status="unverified",
                source="scraped",
            ))

        return contacts

    # ═══════════════════════════════════════════════════════════════════
    #  Strategy 3 — Permutation + DNS/SMTP verification
    # ═══════════════════════════════════════════════════════════════════

    async def _permutate_and_verify(
        self,
        domain: str,
        contacts_hint: Optional[list[str]] = None,
    ) -> List[ContactResult]:
        """
        Generate email permutations from names (or generic guesses),
        verify MX records, then SMTP RCPT TO probe each candidate.
        """
        # Part A — build candidate list
        candidates = self._generate_permutations(domain, contacts_hint)
        if not candidates:
            return []

        # Part B — DNS MX check
        mx_host = await asyncio.to_thread(self._get_mx_host, domain)
        if not mx_host:
            logger.info("No MX records for %s — skipping SMTP verification", domain)
            return []

        # Skip SMTP for major providers (they block RCPT TO probing)
        if domain in MAJOR_PROVIDERS:
            logger.info("Domain %s is a major provider — skipping SMTP", domain)
            return [
                ContactResult(
                    first_name=c.get("first_name"),
                    last_name=c.get("last_name"),
                    full_name=None,
                    designation=None,
                    email=c["email"],
                    email_confidence=40,
                    email_status="unverified",
                    source="permutation",
                )
                for c in candidates
            ]

        # Part C — SMTP RCPT TO verification (sequential with 2s delay)
        results: List[ContactResult] = []
        for i, candidate in enumerate(candidates):
            if i > 0:
                await asyncio.sleep(2)  # 2s delay between checks

            status, confidence = await asyncio.to_thread(
                self._smtp_verify, mx_host, candidate["email"]
            )
            results.append(ContactResult(
                first_name=candidate.get("first_name"),
                last_name=candidate.get("last_name"),
                full_name=None,
                designation=None,
                email=candidate["email"],
                email_confidence=confidence,
                email_status=status,
                source="permutation",
            ))

            # Stop early if we got a verified hit
            if status == "verified" and confidence > 70:
                break

        return results

    # ── Permutation generator ──────────────────────────────────────────

    @staticmethod
    def _generate_permutations(domain: str, names: Optional[list[str]] = None) -> list[dict]:
        """
        Generate email candidates from name hints or generic guesses.
        Returns list of dicts: {email, first_name?, last_name?}
        """
        candidates: list[dict] = []

        if names:
            for name in names:
                parts = name.strip().lower().split()
                if len(parts) < 1:
                    continue
                first = parts[0]
                last = parts[-1] if len(parts) > 1 else None

                perms = [f"{first}@{domain}"]
                if last:
                    perms.extend([
                        f"{first}.{last}@{domain}",
                        f"{first}{last}@{domain}",
                        f"{first[0]}.{last}@{domain}",
                        f"{first[0]}{last}@{domain}",
                        f"{last}@{domain}",
                        f"{first}_{last}@{domain}",
                    ])

                for email in perms:
                    candidates.append({
                        "email": email,
                        "first_name": first.capitalize(),
                        "last_name": last.capitalize() if last else None,
                    })
        else:
            # Generic guesses when no names available
            for prefix in ("hello", "hi", "owner", "founder"):
                candidates.append({
                    "email": f"{prefix}@{domain}",
                    "first_name": None,
                    "last_name": None,
                })

        # Deduplicate by email
        seen: set[str] = set()
        unique: list[dict] = []
        for c in candidates:
            if c["email"] not in seen:
                seen.add(c["email"])
                unique.append(c)

        # Cap at 10 candidates max
        return unique[:10]

    # ── DNS MX check ───────────────────────────────────────────────────

    @staticmethod
    def _get_mx_host(domain: str) -> Optional[str]:
        """Resolve MX records for domain. Return highest-priority host or None."""
        try:
            answers = dns.resolver.resolve(domain, "MX")
            # Sort by preference (lower = higher priority)
            mx_records = sorted(answers, key=lambda r: r.preference)
            if mx_records:
                host = str(mx_records[0].exchange).rstrip(".")
                return host
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            return None
        except Exception as exc:
            logger.warning("DNS MX lookup failed for %s: %s", domain, exc)
            return None
        return None

    # ── SMTP RCPT TO verification ──────────────────────────────────────

    @staticmethod
    def _smtp_verify(mx_host: str, email: str) -> tuple[str, int]:
        """
        Probe the mail server with RCPT TO to check if the address exists.

        Returns (status, confidence):
          - ('verified', 75)   if server returns 250
          - ('invalid', 0)     if server returns 550
          - ('unverified', 40) on connection issues / ambiguous responses
        """
        try:
            with smtplib.SMTP(mx_host, 25, timeout=5) as smtp:
                smtp.ehlo("verify.local")
                smtp.mail("verify@verify.local")
                code, _ = smtp.rcpt(email)

                if code == 250:
                    return ("verified", 75)
                elif code == 550:
                    return ("invalid", 0)
                else:
                    return ("unverified", 40)
        except smtplib.SMTPConnectError:
            return ("unverified", 40)
        except smtplib.SMTPServerDisconnected:
            return ("unverified", 40)
        except socket.timeout:
            return ("unverified", 40)
        except OSError:
            return ("unverified", 40)
        except Exception as exc:
            logger.warning("SMTP verify error for %s: %s", email, exc)
            return ("unverified", 40)

    # ═══════════════════════════════════════════════════════════════════
    #  Utility
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_domain(website: str) -> Optional[str]:
        """
        Clean website URL and return just the domain.
        Remove http(s)://, www., trailing slashes.
        Return None if invalid.
        """
        if not website:
            return None

        url = website.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                return None
            # Strip www.
            if host.startswith("www."):
                host = host[4:]
            # Basic sanity: must have at least one dot
            if "." not in host:
                return None
            return host.lower()
        except Exception:
            return None
