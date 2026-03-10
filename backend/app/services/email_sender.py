"""
Email Sender — Brevo SMTP sending + daily limit tracking.

Classes:
  BrevoEmailSender  — build MIME & send via SMTP
  DailyLimitTracker — Redis-backed per-campaign daily send counter
"""

from __future__ import annotations

import logging
import re
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import redis

from app.config import settings
from app.database import supabase

logger = logging.getLogger(__name__)

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class SendResult:
    success: bool
    message_id: Optional[str]
    error: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════
#  BrevoEmailSender
# ═══════════════════════════════════════════════════════════════════════════


class BrevoEmailSender:
    """Send emails via Brevo SMTP relay."""

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body_html: str,
        tracking_id: str,
        campaign_id: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> SendResult:
        """
        Build MIME message and send via Brevo SMTP.

        The body_html should already contain the tracking pixel
        (injected by CampaignEngine.build_email_for_step).
        """
        sender_email = from_email or settings.BREVO_SENDER_EMAIL
        sender_name = from_name or settings.BREVO_SENDER_NAME

        if not sender_email:
            return SendResult(success=False, message_id=None, error="BREVO_SENDER_EMAIL not set")

        # ── Build MIME ──────────────────────────────────────────────────
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
        msg["Subject"] = subject
        msg["X-Tracking-ID"] = tracking_id
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@{sender_email.split('@')[-1]}?subject=unsubscribe>"

        if campaign_id:
            msg["X-Campaign-ID"] = campaign_id

        # Plain-text fallback (strip HTML tags)
        plain_text = self._strip_html(body_html)
        text_part = MIMEText(plain_text, "plain", "utf-8")
        html_part = MIMEText(body_html, "html", "utf-8")
        msg.attach(text_part)
        msg.attach(html_part)

        # ── Send via SMTP ───────────────────────────────────────────────
        try:
            with smtplib.SMTP(settings.BREVO_SMTP_HOST, settings.BREVO_SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender_email, settings.BREVO_API_KEY)
                server.sendmail(sender_email, to_email, msg.as_string())

            logger.info("Email sent to %s (tracking=%s)", to_email, tracking_id)
            return SendResult(success=True, message_id=tracking_id, error=None)

        except smtplib.SMTPAuthenticationError as exc:
            logger.error("SMTP auth failed: %s", exc)
            return SendResult(success=False, message_id=None, error=f"SMTP auth error: {exc}")
        except smtplib.SMTPRecipientsRefused as exc:
            logger.error("Recipient refused (%s): %s", to_email, exc)
            return SendResult(success=False, message_id=None, error=f"Recipient refused: {exc}")
        except Exception as exc:
            logger.error("SMTP send error: %s", exc)
            return SendResult(success=False, message_id=None, error=str(exc))

    @staticmethod
    def _strip_html(html: str) -> str:
        """Very simple HTML tag stripper for plain-text fallback."""
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# ═══════════════════════════════════════════════════════════════════════════
#  DailyLimitTracker
# ═══════════════════════════════════════════════════════════════════════════


class DailyLimitTracker:
    """Redis-backed per-campaign daily send counter."""

    @staticmethod
    def _key(campaign_id: str) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"send_count:{campaign_id}:{today}"

    def get_sent_today(self, campaign_id: str) -> int:
        if not _redis:
            return 0
        try:
            return int(_redis.get(self._key(campaign_id)) or 0)
        except Exception:
            return 0

    def increment(self, campaign_id: str) -> None:
        if not _redis:
            return
        try:
            key = self._key(campaign_id)
            pipe = _redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 25 * 3600)  # 25h TTL
            pipe.execute()
        except Exception as exc:
            logger.warning("DailyLimitTracker increment failed: %s", exc)

    def can_send(self, campaign_id: str, daily_limit: int) -> bool:
        return self.get_sent_today(campaign_id) < daily_limit


# ═══════════════════════════════════════════════════════════════════════════
#  Legacy wrapper (backward-compat for existing imports)
# ═══════════════════════════════════════════════════════════════════════════


def send_campaign_email(email_log_id: str) -> dict:
    """
    Send an email from email_logs. Used by send_queued_email task.
    """
    log = (
        supabase.table("email_logs")
        .select("*")
        .eq("id", email_log_id)
        .single()
        .execute()
    )
    if not log.data:
        return {"status": "failed", "error": "Email log not found"}

    email_log = log.data

    # Guard: only send if queued or approved
    if email_log.get("status") not in ("queued", "approved"):
        return {"status": "skipped", "error": f"Status is '{email_log.get('status')}', not sendable"}

    # Optimistic lock — mark as 'sending' to prevent double-send
    supabase.table("email_logs").update(
        {"status": "sending"}
    ).eq("id", email_log_id).execute()

    # Fetch contact
    contact = (
        supabase.table("contacts")
        .select("email, full_name, first_name, last_name")
        .eq("id", email_log["contact_id"])
        .single()
        .execute()
    )
    if not contact.data or not contact.data.get("email"):
        supabase.table("email_logs").update({"status": "failed"}).eq("id", email_log_id).execute()
        return {"status": "failed", "error": "Contact email not found"}

    to_name = (
        contact.data.get("full_name")
        or f"{contact.data.get('first_name', '')} {contact.data.get('last_name', '')}".strip()
        or ""
    )

    # Get campaign_id for headers
    campaign_id = None
    if email_log.get("campaign_lead_id"):
        cl = (
            supabase.table("campaign_leads")
            .select("campaign_id")
            .eq("id", email_log["campaign_lead_id"])
            .single()
            .execute()
        )
        if cl.data:
            campaign_id = cl.data["campaign_id"]

    tracking_id = email_log.get("tracking_id") or str(uuid.uuid4())

    sender = BrevoEmailSender()
    result = sender.send_email(
        to_email=contact.data["email"],
        to_name=to_name,
        subject=email_log.get("subject", ""),
        body_html=email_log.get("body", ""),
        tracking_id=tracking_id,
        campaign_id=campaign_id,
    )

    now = datetime.now(timezone.utc).isoformat()

    if result.success:
        supabase.table("email_logs").update({
            "status": "sent",
            "sent_at": now,
            "tracking_id": tracking_id,
        }).eq("id", email_log_id).execute()

        # Increment daily counter
        if campaign_id:
            DailyLimitTracker().increment(campaign_id)

        return {"status": "sent", "tracking_id": tracking_id}
    else:
        supabase.table("email_logs").update({
            "status": "failed",
        }).eq("id", email_log_id).execute()
        return {"status": "failed", "error": result.error}
