"""
Reply Tracker & Sentiment Engine — Module 07

Classes:
  ReplyPoller        — IMAP inbox polling, reply detection, matching
  SentimentClassifier — rule-based sentiment classification (no ML needed)
  BrevoWebhookHandler — process Brevo webhook events

Workflow:
  1. poll_inbox() — connect IMAP, fetch UNSEEN emails from last 24h
  2. match_reply_to_log() — link reply to the email_log that triggered it
  3. process_reply() — update statuses, insert reply record, classify sentiment
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional, List

from app.config import settings
from app.database import supabase

logger = logging.getLogger(__name__)

# Redis for soft-bounce counter
try:
    import redis as _redis_lib
    _redis = _redis_lib.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None
except Exception:
    _redis = None


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class ReplyResult:
    from_email: str
    subject: str
    body_text: str
    body_html: str
    received_at: datetime
    in_reply_to_message_id: Optional[str] = None
    tracking_id: Optional[str] = None
    message_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
#  Sentiment Classifier
# ═══════════════════════════════════════════════════════════════════════════


class SentimentClassifier:
    """
    Rule-based sentiment classification.
    No ML or API calls — cheap and deterministic.
    """

    OOO_KEYWORDS = [
        "out of office", "on vacation", "on leave", "auto-reply",
        "automatic reply", "currently away", "away from",
        "i am on leave", "be back on", "return on", "return to office",
        "limited access to email",
    ]

    UNSUB_KEYWORDS = [
        "unsubscribe", "remove me", "stop emailing", "don't contact",
        "do not contact", "not interested", "please stop", "opt out",
        "take me off", "remove from list", "stop sending",
    ]

    POSITIVE_KEYWORDS = [
        "interested", "sounds good", "tell me more", "let's chat",
        "lets chat", "book a call", "when can we", "love to learn",
        "yes", "great timing", "we've been looking", "we have been looking",
        "let's talk", "lets talk", "schedule a call", "set up a meeting",
        "absolutely", "perfect timing", "would love to", "i'd like to",
        "send me more", "curious about",
    ]

    NEGATIVE_KEYWORDS = [
        "not interested", "no thanks", "no thank you", "we're good",
        "we are good", "already have", "not the right time", "budget",
        "not a fit", "not looking", "pass on this", "decided to go with",
        "found another", "not at this time", "maybe later",
    ]

    @classmethod
    def classify(cls, body: str) -> str:
        """
        Classify reply body text into a sentiment bucket.

        Returns: 'out-of-office' | 'unsubscribe' | 'positive' | 'negative' | 'neutral'
        """
        if not body:
            return "neutral"

        lower = body.lower().strip()

        # 1. Out of office (checked first — usually auto-generated)
        if any(kw in lower for kw in cls.OOO_KEYWORDS):
            return "out-of-office"

        # 2. Unsubscribe request
        if any(kw in lower for kw in cls.UNSUB_KEYWORDS):
            return "unsubscribe"

        # 3. Positive signals (need 2+ keyword matches for confidence)
        positive_hits = sum(1 for kw in cls.POSITIVE_KEYWORDS if kw in lower)
        if positive_hits >= 2:
            return "positive"

        # 4. Negative signals (1 is enough)
        if any(kw in lower for kw in cls.NEGATIVE_KEYWORDS):
            return "negative"

        # 5. Single positive keyword still counts as positive
        if positive_hits == 1:
            return "positive"

        return "neutral"


# ═══════════════════════════════════════════════════════════════════════════
#  Reply Poller
# ═══════════════════════════════════════════════════════════════════════════


class ReplyPoller:
    """
    Polls the sending inbox via IMAP to detect replies.
    Brevo webhooks don't fire on replies, so we need IMAP.
    """

    def __init__(self):
        self.host = settings.IMAP_HOST
        self.port = settings.IMAP_PORT
        self.user = settings.IMAP_USER
        self.password = settings.IMAP_PASSWORD
        self.classifier = SentimentClassifier()

    # ── IMAP Connection ────────────────────────────────────────────────

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Establish authenticated IMAP connection."""
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        conn.login(self.user, self.password)
        return conn

    # ── Parse Email ────────────────────────────────────────────────────

    @staticmethod
    def _decode_header_value(raw) -> str:
        """Safely decode an email header value."""
        if raw is None:
            return ""
        parts = decode_header(str(raw))
        decoded = []
        for data, charset in parts:
            if isinstance(data, bytes):
                decoded.append(data.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(data))
        return " ".join(decoded).strip()

    @staticmethod
    def _extract_body(msg: email.message.Message) -> tuple:
        """
        Walk MIME structure, return (plain_text, html_text).
        """
        text_body = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, errors="replace")
                except Exception:
                    continue

                if ctype == "text/plain":
                    text_body = decoded
                elif ctype == "text/html":
                    html_body = decoded
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace") if payload else ""
            except Exception:
                decoded = ""

            if msg.get_content_type() == "text/html":
                html_body = decoded
            else:
                text_body = decoded

        return text_body, html_body

    @staticmethod
    def _extract_tracking_id(body: str) -> Optional[str]:
        """
        Search for our tracking pixel URL in the email body.
        Pattern: /track/open/{tracking_id}
        """
        match = re.search(r"/track/open/([a-f0-9\-]{36})", body)
        return match.group(1) if match else None

    # ── Poll Inbox ─────────────────────────────────────────────────────

    def poll_inbox(self) -> List[ReplyResult]:
        """
        Connect IMAP, search for UNSEEN emails from last 24h, parse them.
        Returns list of ReplyResult.
        """
        if not all([self.host, self.user, self.password]):
            logger.warning("IMAP not configured — skipping reply polling")
            return []

        results: List[ReplyResult] = []

        try:
            conn = self._connect()
            conn.select("INBOX")

            # Search for UNSEEN emails from last 24h
            since_date = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%d-%b-%Y")
            status, msg_ids = conn.search(None, f'(UNSEEN SINCE {since_date})')

            if status != "OK" or not msg_ids[0]:
                conn.logout()
                return []

            ids = msg_ids[0].split()
            logger.info("Found %d unseen emails to process", len(ids))

            for msg_id in ids:
                try:
                    status, msg_data = conn.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    from_email = email.utils.parseaddr(msg.get("From", ""))[1]
                    subject = self._decode_header_value(msg.get("Subject", ""))
                    in_reply_to = msg.get("In-Reply-To", "").strip() or None
                    message_id_hdr = msg.get("Message-ID", "").strip() or None

                    # Parse received date
                    date_str = msg.get("Date", "")
                    try:
                        received_at = parsedate_to_datetime(date_str)
                        if received_at.tzinfo is None:
                            received_at = received_at.replace(tzinfo=timezone.utc)
                    except Exception:
                        received_at = datetime.now(timezone.utc)

                    # Extract body
                    text_body, html_body = self._extract_body(msg)

                    # Try to find tracking ID in body
                    combined = html_body or text_body
                    tracking_id = self._extract_tracking_id(combined)

                    results.append(ReplyResult(
                        from_email=from_email.lower(),
                        subject=subject,
                        body_text=text_body,
                        body_html=html_body,
                        received_at=received_at,
                        in_reply_to_message_id=in_reply_to,
                        tracking_id=tracking_id,
                        message_id=message_id_hdr,
                    ))

                    # Mark as SEEN after processing
                    conn.store(msg_id, "+FLAGS", "\\Seen")

                except Exception as exc:
                    logger.warning("Error parsing email %s: %s", msg_id, exc)
                    continue

            conn.logout()

        except imaplib.IMAP4.error as exc:
            logger.error("IMAP connection error: %s", exc)
        except Exception as exc:
            logger.error("Reply polling error: %s", exc)

        return results

    # ── Match Reply to Email Log ───────────────────────────────────────

    def match_reply_to_log(self, reply: ReplyResult) -> Optional[str]:
        """
        Attempt to find the matching email_log_id for a reply.

        Strategy (ordered by confidence):
          1. tracking_id found in body → exact match
          2. In-Reply-To header → match message_id (stored as tracking_id)
          3. from_email matches a contact → find most recent sent email_log
        """
        # Strategy 1: tracking_id in body
        if reply.tracking_id:
            result = (
                supabase.table("email_logs")
                .select("id")
                .eq("tracking_id", reply.tracking_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]

        # Strategy 2: In-Reply-To → match tracking_id (used as Message-ID)
        if reply.in_reply_to_message_id:
            # Clean angle brackets from In-Reply-To
            clean_id = reply.in_reply_to_message_id.strip("<>")
            result = (
                supabase.table("email_logs")
                .select("id")
                .eq("tracking_id", clean_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]

        # Strategy 3: Match by sender email → most recent sent log
        contacts = (
            supabase.table("contacts")
            .select("id")
            .eq("email", reply.from_email)
            .execute()
        )
        if contacts.data:
            contact_ids = [c["id"] for c in contacts.data]
            for cid in contact_ids:
                result = (
                    supabase.table("email_logs")
                    .select("id")
                    .eq("contact_id", cid)
                    .eq("status", "sent")
                    .order("sent_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]["id"]

        return None

    # ── Process Reply ──────────────────────────────────────────────────

    def process_reply(self, reply: ReplyResult, email_log_id: str) -> dict:
        """
        Process a matched reply:
          1. Update email_log → status='replied', replied_at
          2. Insert into replies table
          3. Classify sentiment
          4. Handle sentiment-specific actions
          5. Pause sequence (unless out-of-office)
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Get email_log details
        log = (
            supabase.table("email_logs")
            .select("campaign_lead_id, contact_id")
            .eq("id", email_log_id)
            .single()
            .execute()
        )
        if not log.data:
            return {"status": "error", "detail": "email_log not found"}

        email_log = log.data

        # Idempotency check — don't process same reply twice
        existing = (
            supabase.table("replies")
            .select("id")
            .eq("email_log_id", email_log_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.info("Reply for email_log %s already processed — skipping", email_log_id)
            return {"status": "skipped", "detail": "already_processed"}

        # 1. Update email_log
        supabase.table("email_logs").update({
            "replied_at": now_iso,
            "status": "replied",
        }).eq("id", email_log_id).execute()

        # 2. Classify sentiment
        sentiment = self.classifier.classify(reply.body_text or reply.body_html)

        # 3. Insert reply record
        reply_data = {
            "email_log_id": email_log_id,
            "contact_id": email_log.get("contact_id"),
            "received_at": reply.received_at.isoformat(),
            "subject": reply.subject,
            "body": reply.body_text or reply.body_html,
            "sentiment": sentiment,
            "is_read": False,
            "raw_payload": {
                "from_email": reply.from_email,
                "body_html": reply.body_html[:5000] if reply.body_html else None,
                "in_reply_to": reply.in_reply_to_message_id,
            },
        }
        supabase.table("replies").insert(reply_data).execute()

        # 4. Sentiment-specific actions
        campaign_lead_id = email_log.get("campaign_lead_id")

        if sentiment == "out-of-office":
            # Do NOT pause sequence — delay next step by 7 days instead
            if campaign_lead_id:
                delay_until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                supabase.table("campaign_leads").update({
                    "next_send_at": delay_until,
                }).eq("id", campaign_lead_id).execute()
            logger.info("OOO reply for email_log %s — delaying next step by 7 days", email_log_id)

        elif sentiment == "unsubscribe":
            # Unsubscribe: stop sequence + flag lead
            if campaign_lead_id:
                supabase.table("campaign_leads").update({
                    "status": "unsubscribed",
                }).eq("id", campaign_lead_id).execute()

                # Get lead_id to add tag
                cl = (
                    supabase.table("campaign_leads")
                    .select("lead_id")
                    .eq("id", campaign_lead_id)
                    .single()
                    .execute()
                )
                if cl.data:
                    lead_id = cl.data["lead_id"]
                    lead = (
                        supabase.table("leads")
                        .select("tags")
                        .eq("id", lead_id)
                        .single()
                        .execute()
                    )
                    if lead.data:
                        tags = lead.data.get("tags") or []
                        if "unsubscribed" not in tags:
                            tags.append("unsubscribed")
                        supabase.table("leads").update({
                            "tags": tags,
                            "status": "dead",
                        }).eq("id", lead_id).execute()

            logger.info("Unsubscribe reply for email_log %s — lead unsubscribed", email_log_id)

        else:
            # Positive / negative / neutral — pause sequence (lead replied)
            if campaign_lead_id:
                supabase.table("campaign_leads").update({
                    "status": "replied",
                }).eq("id", campaign_lead_id).execute()

                # Update lead status
                cl = (
                    supabase.table("campaign_leads")
                    .select("lead_id")
                    .eq("id", campaign_lead_id)
                    .single()
                    .execute()
                )
                if cl.data:
                    supabase.table("leads").update({
                        "status": "replied",
                    }).eq("id", cl.data["lead_id"]).execute()

            logger.info("Reply (%s) for email_log %s — sequence paused", sentiment, email_log_id)

        return {
            "status": "processed",
            "sentiment": sentiment,
            "email_log_id": email_log_id,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Brevo Webhook Event Handler
# ═══════════════════════════════════════════════════════════════════════════


class BrevoWebhookHandler:
    """
    Handles Brevo webhook events: delivered, opened, clicked,
    hard_bounce, soft_bounce, unsubscribe, spam, invalid_email.
    """

    @staticmethod
    def handle_event(event_type: str, payload: dict) -> dict:
        """
        Process a single Brevo webhook event.
        Always returns immediately — Brevo retries on non-200.
        """
        event_email = payload.get("email", "").lower()
        message_id = payload.get("message-id") or payload.get("message_id", "")
        event_date = payload.get("date") or payload.get("ts_event")

        # Find the email_log by message_id (tracking_id)
        log = None
        if message_id:
            result = (
                supabase.table("email_logs")
                .select("id, campaign_lead_id, contact_id, status")
                .eq("tracking_id", message_id)
                .limit(1)
                .execute()
            )
            if result.data:
                log = result.data[0]

        # If no log found by message_id, try by contact email (most recent)
        if not log and event_email:
            contacts = (
                supabase.table("contacts")
                .select("id")
                .eq("email", event_email)
                .limit(1)
                .execute()
            )
            if contacts.data:
                result = (
                    supabase.table("email_logs")
                    .select("id, campaign_lead_id, contact_id, status")
                    .eq("contact_id", contacts.data[0]["id"])
                    .eq("status", "sent")
                    .order("sent_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    log = result.data[0]

        if not log:
            logger.warning("Brevo webhook: no matching email_log for event=%s email=%s", event_type, event_email)
            return {"status": "no_match"}

        log_id = log["id"]
        now_iso = datetime.now(timezone.utc).isoformat()

        # ── Handle event types ─────────────────────────────────────────

        if event_type == "opened":
            supabase.table("email_logs").update({
                "opened_at": now_iso,
                "status": "opened",
            }).eq("id", log_id).is_("opened_at", "null").execute()
            return {"status": "updated", "event": "opened"}

        elif event_type == "clicked":
            supabase.table("email_logs").update({
                "clicked_at": now_iso,
                "status": "clicked",
            }).eq("id", log_id).execute()
            return {"status": "updated", "event": "clicked"}

        elif event_type == "hard_bounce":
            supabase.table("email_logs").update({
                "status": "bounced",
            }).eq("id", log_id).execute()

            # Mark contact as bounced
            if log.get("contact_id"):
                supabase.table("contacts").update({
                    "email_status": "bounced",
                }).eq("id", log["contact_id"]).execute()

            # Pause campaign_lead
            if log.get("campaign_lead_id"):
                supabase.table("campaign_leads").update({
                    "status": "paused",
                }).eq("id", log["campaign_lead_id"]).execute()

            return {"status": "updated", "event": "hard_bounce"}

        elif event_type == "soft_bounce":
            # Track soft bounces in Redis — 2+ becomes hard bounce
            bounce_key = f"soft_bounce:{event_email}"
            bounce_count = 1
            if _redis:
                try:
                    bounce_count = _redis.incr(bounce_key)
                    _redis.expire(bounce_key, 7 * 86400)  # 7 day TTL
                except Exception:
                    pass

            if bounce_count >= 2:
                # Treat as hard bounce
                return BrevoWebhookHandler.handle_event("hard_bounce", payload)

            return {"status": "soft_bounce_tracked", "count": bounce_count}

        elif event_type in ("unsubscribe", "spam"):
            # Unsubscribe or spam complaint
            if log.get("campaign_lead_id"):
                supabase.table("campaign_leads").update({
                    "status": "unsubscribed",
                }).eq("id", log["campaign_lead_id"]).execute()

                # Get lead_id and add tag
                cl = (
                    supabase.table("campaign_leads")
                    .select("lead_id")
                    .eq("id", log["campaign_lead_id"])
                    .single()
                    .execute()
                )
                if cl.data:
                    lead = (
                        supabase.table("leads")
                        .select("tags")
                        .eq("id", cl.data["lead_id"])
                        .single()
                        .execute()
                    )
                    if lead.data:
                        tags = lead.data.get("tags") or []
                        tag_to_add = "spam_reported" if event_type == "spam" else "unsubscribed"
                        if tag_to_add not in tags:
                            tags.append(tag_to_add)
                        supabase.table("leads").update({
                            "tags": tags,
                            "status": "dead",
                        }).eq("id", cl.data["lead_id"]).execute()

            return {"status": "updated", "event": event_type}

        elif event_type == "invalid_email":
            if log.get("contact_id"):
                supabase.table("contacts").update({
                    "email_status": "invalid",
                }).eq("id", log["contact_id"]).execute()
            return {"status": "updated", "event": "invalid_email"}

        elif event_type == "delivered":
            # Just log it — status stays 'sent'
            return {"status": "delivered_noted"}

        return {"status": "unhandled_event", "event": event_type}
