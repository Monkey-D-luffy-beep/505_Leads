"""
Signal Engine — Detects buying signals from lead data.

Three tiers:
  Tier 1 — Universal signals (always run): website, SSL, reviews, phone, etc.
  Tier 2 — Tech signals (always collected): CMS, analytics, chat, CRM, ads, etc.
  Tier 3 — Campaign signals (user-defined via UI, keyword-based detection)
"""

import re
import random
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional

import httpx
from bs4 import BeautifulSoup

from app.database import supabase

logger = logging.getLogger(__name__)

# ── User-agent for outbound HTTP fetches ───────────────────────────────────
_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


@dataclass
class SignalResult:
    """Single signal detection outcome."""

    signal_key: str
    signal_value: str  # human-readable reason / evidence
    detected: bool
    score_contribution: int  # raw weight if detected, 0 if not


# ═══════════════════════════════════════════════════════════════════════════
#  Signal Engine
# ═══════════════════════════════════════════════════════════════════════════


class SignalEngine:
    """Detect Tier 1 + Tier 2 + Tier 3 signals for a lead."""

    # ── public API ─────────────────────────────────────────────────────────

    async def detect_all_signals(
        self, lead: Dict[str, Any], raw_data: Dict[str, Any]
    ) -> List[SignalResult]:
        """
        Run every active signal definition against *lead* and its *raw_data*.

        Returns a list of SignalResult for every signal — detected or not.
        """
        # Load active signal definitions
        defs = (
            supabase.table("signal_definitions")
            .select("*")
            .eq("is_active", True)
            .execute()
        )
        definitions: List[Dict] = defs.data or []

        # Pre-fetch website HTML + tech stack once (shared by many checks)
        website_meta: Dict = raw_data.get("website_meta", {})
        website_url: Optional[str] = lead.get("website") or raw_data.get("website")
        html: str = ""
        html_lower: str = ""

        if website_url:
            html = await self._fetch_html(website_url)
            html_lower = html.lower()

        tech_stack = self._detect_tech_stack(html_lower) if html else {}

        results: List[SignalResult] = []

        for defn in definitions:
            key = defn["signal_key"]
            weight = defn.get("default_weight", 10)
            tier = defn.get("tier")

            result: Optional[SignalResult] = None

            # ── Tier 1: Universal ──────────────────────────────────────
            if tier == 1:
                result = self._run_tier1(key, weight, lead, raw_data, website_meta, html_lower)

            # ── Tier 2: Tech ───────────────────────────────────────────
            elif tier == 2:
                result = self._run_tier2(key, weight, tech_stack, website_meta)

            # ── Tier 3: Custom / keyword-based ─────────────────────────
            elif tier == 3:
                result = self._run_tier3(key, weight, defn, raw_data, html_lower)

            if result is not None:
                results.append(result)

        return results

    # ── Tier 1 dispatcher ──────────────────────────────────────────────────

    def _run_tier1(
        self,
        key: str,
        weight: int,
        lead: Dict,
        raw_data: Dict,
        website_meta: Dict,
        html_lower: str,
    ) -> SignalResult:
        handlers = {
            "has_website": self._check_has_website,
            "has_ssl": self._check_has_ssl,
            "is_mobile_friendly": self._check_is_mobile_friendly,
            "has_social_presence": self._check_has_social_presence,
            "has_google_reviews": self._check_has_google_reviews,
            "high_rating": self._check_high_rating,
            "low_review_count": self._check_low_review_count,
            "has_contact_form": self._check_has_contact_form,
            "has_phone_number": self._check_has_phone,
            "small_business": self._check_small_business,
        }

        handler = handlers.get(key)
        if handler:
            detected, value = handler(lead=lead, raw_data=raw_data, website_meta=website_meta, html_lower=html_lower)
            return SignalResult(
                signal_key=key,
                signal_value=value,
                detected=detected,
                score_contribution=weight if detected else 0,
            )

        # Unknown Tier 1 key — skip gracefully
        return SignalResult(signal_key=key, signal_value="unknown check", detected=False, score_contribution=0)

    # ── Tier 2 dispatcher ──────────────────────────────────────────────────

    def _run_tier2(
        self, key: str, weight: int, tech_stack: Dict, website_meta: Dict
    ) -> SignalResult:
        handlers = {
            "uses_wordpress": lambda: (tech_stack.get("cms") == "wordpress", "wp-content detected"),
            "uses_wix_squarespace": lambda: (
                tech_stack.get("cms") in ("wix", "squarespace"),
                f"{tech_stack.get('cms', 'none')} detected",
            ),
            "uses_shopify": lambda: (tech_stack.get("has_shopify", False), "cdn.shopify.com detected"),
            "no_analytics": lambda: (not tech_stack.get("has_analytics", False), "No analytics tool found"),
            "no_chat_tool": lambda: (not tech_stack.get("has_chat", False), "No live chat tool found"),
            "no_crm_pixel": lambda: (
                not any(tech_stack.get(k, False) for k in ("has_hubspot", "has_intercom", "has_drift")),
                "No CRM pixel found",
            ),
            "runs_paid_ads": lambda: (
                tech_stack.get("has_google_ads", False) or tech_stack.get("has_meta_pixel", False),
                "Paid ads pixel detected",
            ),
            "has_booking_widget": lambda: (
                tech_stack.get("has_booking", False) or website_meta.get("has_booking_widget", False),
                "Booking widget detected",
            ),
            "no_booking_widget": lambda: (
                not tech_stack.get("has_booking", False) and not website_meta.get("has_booking_widget", False),
                "No booking widget found",
            ),
            "old_cms_version": lambda: (tech_stack.get("old_cms", False), "Outdated CMS version"),
            "no_email_marketing": lambda: (
                not tech_stack.get("has_mailchimp", False) and not tech_stack.get("has_klaviyo", False),
                "No email marketing tool found",
            ),
        }

        handler = handlers.get(key)
        if handler:
            detected, value = handler()
            return SignalResult(
                signal_key=key,
                signal_value=value,
                detected=detected,
                score_contribution=weight if detected else 0,
            )

        return SignalResult(signal_key=key, signal_value="unknown tech check", detected=False, score_contribution=0)

    # ── Tier 3 dispatcher ──────────────────────────────────────────────────

    def _run_tier3(
        self,
        key: str,
        weight: int,
        defn: Dict,
        raw_data: Dict,
        html_lower: str,
    ) -> SignalResult:
        """Tier 3 signals use detection_logic.keywords from the definition."""
        logic = defn.get("detection_logic") or {}
        keywords = logic.get("keywords", [])
        search_text = html_lower + " " + str(raw_data.get("website_meta", {})).lower()

        for kw in keywords:
            if kw.lower() in search_text:
                return SignalResult(
                    signal_key=key,
                    signal_value=f"Keyword '{kw}' found",
                    detected=True,
                    score_contribution=weight,
                )

        return SignalResult(
            signal_key=key,
            signal_value="No matching keywords",
            detected=False,
            score_contribution=0,
        )

    # ═══════════════════════════════════════════════════════════════════════
    #  Tier 1 — individual check methods
    # ═══════════════════════════════════════════════════════════════════════

    def _check_has_website(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        url = lead.get("website") or raw_data.get("website")
        return (url is not None and url != ""), f"website={url}"

    def _check_has_ssl(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        url = lead.get("website") or raw_data.get("website") or ""
        has = url.startswith("https://")
        return has, f"{'HTTPS' if has else 'no HTTPS'}"

    def _check_is_mobile_friendly(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        # Check for viewport meta tag or responsive CSS
        has_viewport = 'name="viewport"' in html_lower or "name='viewport'" in html_lower
        has_media = "@media" in html_lower
        responsive = has_viewport or has_media
        return responsive, f"viewport={'yes' if has_viewport else 'no'}, media_queries={'yes' if has_media else 'no'}"

    def _check_has_social_presence(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        links = website_meta.get("social_links", [])
        has = len(links) > 0
        return has, f"{len(links)} social links"

    def _check_has_google_reviews(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        count = lead.get("google_review_count") or raw_data.get("review_count") or 0
        has = count > 0
        return has, f"{count} reviews"

    def _check_high_rating(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        rating = lead.get("google_rating") or raw_data.get("rating")
        if rating is None:
            return False, "no rating"
        high = float(rating) >= 4.0
        return high, f"rating={rating}"

    def _check_low_review_count(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        count = lead.get("google_review_count") or raw_data.get("review_count") or 0
        low = 0 < count < 20
        return low, f"{count} reviews (<20)"

    def _check_has_contact_form(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        has = website_meta.get("has_contact_form", False)
        return has, f"contact_form={'yes' if has else 'no'}"

    def _check_has_phone(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        phone = lead.get("phone") or raw_data.get("phone")
        has = phone is not None and phone != ""
        return has, f"phone={phone}"

    def _check_small_business(self, *, lead: Dict, raw_data: Dict, website_meta: Dict, html_lower: str):
        estimate = lead.get("employee_estimate") or ""
        category = lead.get("industry") or raw_data.get("category") or ""
        combined = (estimate + " " + category).lower()

        # Markers of small businesses
        small_markers = [
            "1-10", "1-20", "2-10", "1-5", "5-10", "10-20",
            "self-employed", "sole", "freelance", "micro",
            "small", "local", "independent",
        ]
        is_small = any(m in combined for m in small_markers)

        # If no estimate at all, default to considering them small
        # (most Google Maps results without size info are small)
        if not estimate:
            is_small = True

        return is_small, f"estimate='{estimate}', category='{category}'"

    # ═══════════════════════════════════════════════════════════════════════
    #  Tech Stack Detection (Tier 2 foundation)
    # ═══════════════════════════════════════════════════════════════════════

    def _detect_tech_stack(self, html_lower: str) -> Dict[str, Any]:
        """
        Scan HTML source for fingerprints of CMS, analytics, chat,
        CRM, ads, booking, and email marketing tools.

        Returns a flat dict of booleans + a `cms` string key.
        """
        result: Dict[str, Any] = {
            "cms": None,
            "has_shopify": False,
            "has_analytics": False,
            "has_chat": False,
            "has_hubspot": False,
            "has_intercom": False,
            "has_drift": False,
            "has_google_ads": False,
            "has_meta_pixel": False,
            "has_booking": False,
            "has_mailchimp": False,
            "has_klaviyo": False,
            "old_cms": False,
        }

        if not html_lower:
            return result

        # ── CMS detection ──────────────────────────────────────────────
        if "/wp-content/" in html_lower or "/wp-includes/" in html_lower:
            result["cms"] = "wordpress"
            # Old WordPress: look for very old version meta
            ver_match = re.search(r'<meta[^>]*generator[^>]*wordpress\s+([\d.]+)', html_lower)
            if ver_match:
                try:
                    major = float(ver_match.group(1).split(".")[0])
                    if major < 6:
                        result["old_cms"] = True
                except ValueError:
                    pass
        elif "wix.com" in html_lower or "wixstatic.com" in html_lower:
            result["cms"] = "wix"
        elif "squarespace.com" in html_lower or "sqsp.net" in html_lower:
            result["cms"] = "squarespace"
        elif "cdn.shopify.com" in html_lower or "myshopify.com" in html_lower:
            result["cms"] = "shopify"
            result["has_shopify"] = True

        # Explicit Shopify check even if CMS already set to something else
        if "cdn.shopify.com" in html_lower:
            result["has_shopify"] = True

        # ── Analytics ──────────────────────────────────────────────────
        analytics_sigs = [
            "gtag(", "analytics.js", "googletagmanager.com",
            "google-analytics.com", "ga('create",
            "plausible.io", "fathom.js", "matomo",
        ]
        result["has_analytics"] = any(sig in html_lower for sig in analytics_sigs)

        # ── Meta Pixel ─────────────────────────────────────────────────
        result["has_meta_pixel"] = (
            "connect.facebook.net" in html_lower
            or "fbq(" in html_lower
            or "facebook pixel" in html_lower
        )

        # ── Google Ads ─────────────────────────────────────────────────
        result["has_google_ads"] = (
            "googleadservices.com" in html_lower
            or "googlesyndication.com" in html_lower
            or "adsbygoogle" in html_lower
        )

        # ── Chat tools ─────────────────────────────────────────────────
        chat_sigs = [
            "intercom.io", "widget.intercom.io",
            "js.driftt.com", "drift.com",
            "tawk.to", "livechat", "zendesk.com",
            "crisp.chat", "tidio.co", "olark.com",
        ]
        result["has_chat"] = any(sig in html_lower for sig in chat_sigs)
        result["has_intercom"] = "intercom.io" in html_lower
        result["has_drift"] = "driftt.com" in html_lower or "drift.com" in html_lower

        # ── CRM / HubSpot ─────────────────────────────────────────────
        result["has_hubspot"] = (
            "js.hs-scripts.com" in html_lower
            or "hubspot.com" in html_lower
            or "hs-analytics" in html_lower
        )

        # ── Booking widgets ────────────────────────────────────────────
        booking_sigs = [
            "calendly.com", "acuityscheduling.com",
            "booksy.com", "setmore.com", "square.site/book",
            "simplybook.me",
        ]
        result["has_booking"] = any(sig in html_lower for sig in booking_sigs)

        # ── Email marketing ────────────────────────────────────────────
        result["has_mailchimp"] = (
            "chimpstatic.com" in html_lower
            or "list-manage.com" in html_lower
            or "mailchimp.com" in html_lower
        )
        result["has_klaviyo"] = (
            "klaviyo.com" in html_lower or "a.]klaviyo.com" in html_lower
        )

        return result

    # ── HTML fetcher (lightweight, no Playwright) ──────────────────────────

    async def _fetch_html(self, url: str) -> str:
        """Download HTML source of a URL via httpx (10 s timeout)."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=10.0,
                headers={"User-Agent": random.choice(_UA)},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        except Exception as exc:
            logger.warning("Failed to fetch HTML from %s: %s", url, exc)
            return ""


# ═══════════════════════════════════════════════════════════════════════════
#  Convenience helpers
# ═══════════════════════════════════════════════════════════════════════════


async def get_signals_for_lead(lead_id: str) -> List[Dict]:
    """Get all detected signals for a lead from the DB."""
    result = supabase.table("signals").select("*").eq("lead_id", lead_id).execute()
    return result.data
