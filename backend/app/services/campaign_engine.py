"""
Campaign Engine — lead enrollment, email assembly, sequence advancement.

Handles:
  - enroll_leads: filter leads by score/signals/geo, assign best contact
  - build_email_for_step: personalize templates with variables + conditional blocks
  - get_due_sends: find campaign_leads ready for next email
  - advance_sequence: move to next step or mark complete
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.config import settings
from app.database import supabase

logger = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────────


@dataclass
class EmailDraft:
    to_email: str
    to_name: str
    subject: str
    body: str
    variant: str              # 'a' or 'b'
    campaign_lead_id: str
    sequence_id: str
    tracking_id: str


# Human-readable hook sentences keyed by signal_key
SIGNAL_HOOKS: dict[str, str] = {
    "no_analytics": "I noticed your site doesn't have any analytics tracking set up",
    "no_booking_widget": "I noticed you don't have an online booking system",
    "uses_wordpress": "I can see your site runs on WordPress",
    "uses_wix_squarespace": "I noticed your site is on Wix or Squarespace",
    "uses_shopify": "I can see you have a Shopify store",
    "runs_paid_ads": "I can see you're running paid ads",
    "low_review_count": "I noticed you have a strong rating but only a few reviews",
    "no_crm_pixel": "It looks like you might not have a CRM connected to your site",
    "no_chat_tool": "I noticed you don't have a live chat tool on your website",
    "no_email_marketing": "I noticed you don't seem to have an email marketing tool set up",
    "has_contact_form": "I can see you have a contact form on your site",
    "has_website": "I took a look at your website",
    "has_ssl": "I see your website is properly secured with SSL",
    "is_mobile_friendly": "Your website looks great on mobile",
    "has_social_presence": "I noticed you're active on social media",
    "has_google_reviews": "I can see you have Google reviews",
    "high_rating": "I noticed you have a great Google rating",
    "has_phone_number": "I see you have a phone number listed",
    "small_business": "As a small business owner, I'm sure you're juggling a lot",
    "old_cms_version": "I noticed your website CMS might need an update",
}


# ═══════════════════════════════════════════════════════════════════════════
#  CampaignEngine
# ═══════════════════════════════════════════════════════════════════════════


class CampaignEngine:
    """Core campaign logic — enrollment, email build, scheduling."""

    # ───────────────────────────────────────────────────────────────────
    #  enroll_leads
    # ───────────────────────────────────────────────────────────────────

    def enroll_leads(self, campaign_id: str) -> dict:
        """
        Find qualifying leads and enroll them into the campaign.

        Returns dict with enrolled / skipped counts.
        """
        # 1. Fetch campaign
        campaign = (
            supabase.table("campaigns")
            .select("*")
            .eq("id", campaign_id)
            .single()
            .execute()
        ).data
        if not campaign:
            return {"error": "campaign_not_found"}

        target = campaign.get("target_filters") or {}
        min_score = campaign.get("min_score", 0)

        # 2. Query eligible leads: scored + min score
        query = (
            supabase.table("leads")
            .select("*")
            .gte("lead_score", min_score)
            .eq("status", "scored")
        )

        # Apply target_filters
        if target.get("country"):
            query = query.eq("country", target["country"])
        if target.get("city"):
            query = query.eq("city", target["city"])
        if target.get("industry"):
            query = query.eq("industry", target["industry"])

        leads_result = query.execute()
        candidates = leads_result.data or []

        # Filter by tags (lead must have at least one matching tag)
        filter_tags = target.get("tags") or []
        if filter_tags:
            tag_set = set(filter_tags)
            candidates = [
                l for l in candidates
                if set(l.get("tags") or []) & tag_set
            ]

        # Filter by required_signals / excluded_signals
        required_signals = set(target.get("required_signals") or [])
        excluded_signals = set(target.get("excluded_signals") or [])

        if required_signals or excluded_signals:
            candidates = self._filter_by_signals(
                candidates, required_signals, excluded_signals
            )

        # 3. Enroll each qualifying lead
        # Get already-enrolled lead_ids for this campaign
        existing = (
            supabase.table("campaign_leads")
            .select("lead_id")
            .eq("campaign_id", campaign_id)
            .execute()
        )
        enrolled_ids = {row["lead_id"] for row in (existing.data or [])}

        # First sequence step for delay calculation
        first_step = (
            supabase.table("sequences")
            .select("delay_days")
            .eq("campaign_id", campaign_id)
            .eq("step_number", 1)
            .limit(1)
            .execute()
        )
        step_delay = 0
        if first_step.data:
            step_delay = first_step.data[0].get("delay_days", 0)

        now = datetime.now(timezone.utc)
        next_send = now + timedelta(days=step_delay)

        enrolled = 0
        skipped_no_contact = 0
        skipped_already = 0

        for lead in candidates:
            lead_id = lead["id"]

            if lead_id in enrolled_ids:
                skipped_already += 1
                continue

            # Find best contact (highest confidence, verified preferred)
            best_contact = self._get_best_contact(lead_id)
            if not best_contact:
                skipped_no_contact += 1
                continue

            # Insert into campaign_leads
            supabase.table("campaign_leads").insert({
                "campaign_id": campaign_id,
                "lead_id": lead_id,
                "contact_id": best_contact["id"],
                "current_step": 0,
                "status": "enrolled",
                "next_send_at": next_send.isoformat(),
            }).execute()

            # Update lead status
            supabase.table("leads").update(
                {"status": "in_campaign"}
            ).eq("id", lead_id).execute()

            enrolled += 1

        logger.info(
            "Campaign %s enrollment: %d enrolled, %d skipped (no contact), %d already enrolled",
            campaign_id, enrolled, skipped_no_contact, skipped_already,
        )
        return {
            "enrolled": enrolled,
            "skipped_no_contact": skipped_no_contact,
            "skipped_already_enrolled": skipped_already,
        }

    # ───────────────────────────────────────────────────────────────────
    #  build_email_for_step
    # ───────────────────────────────────────────────────────────────────

    def build_email_for_step(
        self, campaign_lead_id: str, step_number: int
    ) -> Optional[EmailDraft]:
        """
        Assemble a fully personalized email for a campaign_lead at a step.
        Returns EmailDraft or None if data is missing.
        """
        # 1. Fetch campaign_lead with joined data
        cl = (
            supabase.table("campaign_leads")
            .select("*")
            .eq("id", campaign_lead_id)
            .single()
            .execute()
        ).data
        if not cl:
            return None

        campaign_id = cl["campaign_id"]
        lead_id = cl["lead_id"]
        contact_id = cl["contact_id"]

        # Fetch lead, contact, campaign
        lead = (
            supabase.table("leads")
            .select("*")
            .eq("id", lead_id)
            .single()
            .execute()
        ).data
        contact = (
            supabase.table("contacts")
            .select("*")
            .eq("id", contact_id)
            .single()
            .execute()
        ).data
        campaign = (
            supabase.table("campaigns")
            .select("*")
            .eq("id", campaign_id)
            .single()
            .execute()
        ).data

        if not lead or not contact or not campaign:
            logger.error(
                "Missing data for campaign_lead %s (lead=%s contact=%s campaign=%s)",
                campaign_lead_id, bool(lead), bool(contact), bool(campaign),
            )
            return None

        # 2. Fetch sequence step
        seq = (
            supabase.table("sequences")
            .select("*")
            .eq("campaign_id", campaign_id)
            .eq("step_number", step_number)
            .single()
            .execute()
        ).data
        if not seq:
            return None

        # 3. Determine variant (A/B split)
        variant = self._pick_variant(campaign_id, seq)

        # 4. Load template for chosen variant
        subject = seq.get(f"variant_{variant}_subject", "") or ""
        body = seq.get(f"variant_{variant}_body", "") or ""

        # 5. Personalization
        # Fetch signals for this lead
        lead_signals = (
            supabase.table("signals")
            .select("signal_key, signal_value, signal_score")
            .eq("lead_id", lead_id)
            .execute()
        ).data or []
        signal_keys = {s["signal_key"] for s in lead_signals}

        # Standard variable substitution
        variables = {
            "first_name": contact.get("first_name") or "there",
            "company_name": lead.get("company_name") or "",
            "city": lead.get("city") or "",
            "website": lead.get("website") or "",
            "rating": str(lead.get("google_rating") or ""),
            "review_count": str(lead.get("google_review_count") or ""),
            "designation": contact.get("designation") or "",
        }

        # Top signal hook — pick highest-scored detected signal
        top_hook = self._get_top_signal_hook(lead_signals)
        variables["top_signal_hook"] = top_hook

        for key, value in variables.items():
            subject = subject.replace(f"{{{{{key}}}}}", value)
            body = body.replace(f"{{{{{key}}}}}", value)

        # Conditional blocks: [[IF:signal_key]] ... [[END]]
        body = self._process_conditional_blocks(body, signal_keys)
        subject = self._process_conditional_blocks(subject, signal_keys)

        # 6. Generate tracking ID
        tracking_id = str(uuid.uuid4())

        # 7. Add tracking pixel
        backend_url = settings.BACKEND_URL
        pixel = (
            f'<img src="{backend_url}/api/v1/track/open/{tracking_id}" '
            f'width="1" height="1" style="display:none" />'
        )
        body = body + "\n" + pixel

        to_name = (
            contact.get("full_name")
            or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            or "there"
        )

        return EmailDraft(
            to_email=contact["email"],
            to_name=to_name,
            subject=subject,
            body=body,
            variant=variant,
            campaign_lead_id=campaign_lead_id,
            sequence_id=seq["id"],
            tracking_id=tracking_id,
        )

    # ───────────────────────────────────────────────────────────────────
    #  get_due_sends
    # ───────────────────────────────────────────────────────────────────

    def get_due_sends(self, campaign_id: str = None) -> List[str]:
        """
        Return campaign_lead_ids that are due for their next send.

        Conditions:
          - campaign_leads.status in ('enrolled', 'active')
          - campaign_leads.next_send_at <= now()
          - parent campaign status = 'active'
        """
        now = datetime.now(timezone.utc)

        query = (
            supabase.table("campaign_leads")
            .select("id, campaign_id")
            .in_("status", ["enrolled", "active"])
            .lte("next_send_at", now.isoformat())
        )

        if campaign_id:
            query = query.eq("campaign_id", campaign_id)

        result = query.execute()
        if not result.data:
            return []

        # Filter to only campaign_leads whose campaign is active
        campaign_ids = list({row["campaign_id"] for row in result.data})
        active_campaigns_resp = (
            supabase.table("campaigns")
            .select("id")
            .in_("id", campaign_ids)
            .eq("status", "active")
            .execute()
        )
        active_campaign_ids = {c["id"] for c in (active_campaigns_resp.data or [])}

        return [
            row["id"]
            for row in result.data
            if row["campaign_id"] in active_campaign_ids
        ]

    # ───────────────────────────────────────────────────────────────────
    #  advance_sequence
    # ───────────────────────────────────────────────────────────────────

    def advance_sequence(self, campaign_lead_id: str) -> None:
        """
        After a step is sent:
          1. Increment current_step
          2. Check if next step exists
          3. If yes → set next_send_at
          4. If no  → mark completed
        """
        cl = (
            supabase.table("campaign_leads")
            .select("*")
            .eq("id", campaign_lead_id)
            .single()
            .execute()
        ).data
        if not cl:
            return

        next_step = cl["current_step"] + 1

        # Check if next sequence step exists
        seq = (
            supabase.table("sequences")
            .select("delay_days")
            .eq("campaign_id", cl["campaign_id"])
            .eq("step_number", next_step)
            .limit(1)
            .execute()
        )

        if seq.data:
            delay_days = seq.data[0].get("delay_days", 1)
            next_send = datetime.now(timezone.utc) + timedelta(days=delay_days)
            supabase.table("campaign_leads").update({
                "current_step": next_step,
                "status": "active",
                "next_send_at": next_send.isoformat(),
            }).eq("id", campaign_lead_id).execute()
        else:
            # No more steps — sequence complete
            supabase.table("campaign_leads").update({
                "current_step": next_step,
                "status": "completed",
                "next_send_at": None,
            }).eq("id", campaign_lead_id).execute()

    # ═══════════════════════════════════════════════════════════════════
    #  Private helpers
    # ═══════════════════════════════════════════════════════════════════

    def _filter_by_signals(
        self,
        candidates: list[dict],
        required: set[str],
        excluded: set[str],
    ) -> list[dict]:
        """Filter candidates by required/excluded signals."""
        if not required and not excluded:
            return candidates

        lead_ids = [l["id"] for l in candidates]
        if not lead_ids:
            return []

        # Batch-fetch signals for all candidate leads
        signals_resp = (
            supabase.table("signals")
            .select("lead_id, signal_key")
            .in_("lead_id", lead_ids)
            .execute()
        )

        # Build map: lead_id → set of signal_keys
        lead_signals: dict[str, set[str]] = {}
        for s in (signals_resp.data or []):
            lead_signals.setdefault(s["lead_id"], set()).add(s["signal_key"])

        filtered = []
        for lead in candidates:
            keys = lead_signals.get(lead["id"], set())
            if required and not required.issubset(keys):
                continue
            if excluded and keys & excluded:
                continue
            filtered.append(lead)

        return filtered

    def _get_best_contact(self, lead_id: str) -> Optional[dict]:
        """Return the contact with highest confidence (verified preferred)."""
        contacts = (
            supabase.table("contacts")
            .select("*")
            .eq("lead_id", lead_id)
            .order("email_confidence", desc=True)
            .execute()
        ).data or []

        if not contacts:
            return None

        # Prefer verified
        for c in contacts:
            if c.get("email") and c.get("email_status") == "verified":
                return c

        # Fall back to any contact with an email
        for c in contacts:
            if c.get("email"):
                return c

        return None

    def _pick_variant(self, campaign_id: str, seq: dict) -> str:
        """
        Decide A or B based on current split ratio for this campaign.
        If variant A sends are below the split_ratio threshold → A, else → B.
        """
        split_ratio = seq.get("split_ratio", 0.5)

        # Count existing sends for this sequence step
        sent_logs = (
            supabase.table("email_logs")
            .select("variant_sent")
            .eq("sequence_id", seq["id"])
            .in_("status", ["sent", "queued", "approved", "opened", "clicked", "replied"])
            .execute()
        ).data or []

        if not sent_logs:
            return "a"

        a_count = sum(1 for l in sent_logs if l.get("variant_sent") == "a")
        total = len(sent_logs)

        current_a_ratio = a_count / total if total > 0 else 0
        return "a" if current_a_ratio < split_ratio else "b"

    @staticmethod
    def _get_top_signal_hook(lead_signals: list[dict]) -> str:
        """
        Find the highest-scored signal for this lead and return
        its human-readable hook sentence.
        """
        if not lead_signals:
            return "I took a look at your online presence"

        # Sort by signal_score descending
        sorted_signals = sorted(
            lead_signals,
            key=lambda s: s.get("signal_score", 0),
            reverse=True,
        )

        for sig in sorted_signals:
            hook = SIGNAL_HOOKS.get(sig["signal_key"])
            if hook:
                return hook

        return "I took a look at your online presence"

    @staticmethod
    def _process_conditional_blocks(text: str, signal_keys: set[str]) -> str:
        """
        Parse and resolve [[IF:signal_key]] ... [[END]] conditional blocks.

        If signal_key is in signal_keys → keep the inner text.
        Otherwise → remove the entire block including tags.
        """
        pattern = r"\[\[IF:(\w+)\]\](.*?)\[\[END\]\]"

        def replacer(match: re.Match) -> str:
            key = match.group(1)
            content = match.group(2)
            if key in signal_keys:
                return content.strip()
            return ""

        return re.sub(pattern, replacer, text, flags=re.DOTALL)
