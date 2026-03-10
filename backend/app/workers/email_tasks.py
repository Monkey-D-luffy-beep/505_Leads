"""
Celery tasks for email finding and email sending operations.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.services.email_sender import send_campaign_email, DailyLimitTracker, BrevoEmailSender
from app.services.email_finder import EmailFinder
from app.database import supabase

logger = logging.getLogger(__name__)

daily_tracker = DailyLimitTracker()


# ═══════════════════════════════════════════════════════════════════════════
#  Email-finding tasks
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    bind=True,
    name="email_tasks.find_emails_for_lead",
    max_retries=3,
    default_retry_delay=30,
    queue="default",
)
def find_emails_for_lead(self, lead_id: str):
    """
    Multi-strategy email finding for a single lead.

    Pipeline:
      1. Fetch lead (with raw_data) from Supabase
      2. Extract domain from lead['website']
      3. Run EmailFinder().find_email(lead)
      4. Upsert results into contacts table (dedup by email)
      5. Update lead status if ≥1 verified email found
    """
    try:
        # 1. Fetch lead
        lead_resp = (
            supabase.table("leads")
            .select("*")
            .eq("id", lead_id)
            .single()
            .execute()
        )
        lead = lead_resp.data
        if not lead:
            logger.error("Lead %s not found", lead_id)
            return {"status": "error", "detail": "lead_not_found"}

        # 2. Check website
        website = lead.get("website")
        if not website:
            logger.info("Lead %s has no website — skipping email find", lead_id)
            supabase.table("leads").update(
                {"notes": "No website — email finding skipped"}
            ).eq("id", lead_id).execute()
            return {"status": "skipped", "detail": "no_website"}

        # 3. Run email finder
        finder = EmailFinder()
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(finder.find_email(lead))
        finally:
            loop.close()

        if not results:
            logger.info("No emails found for lead %s", lead_id)
            return {"status": "completed", "contacts_found": 0}

        # 4. Upsert into contacts table (dedup by email per lead)
        existing_contacts = (
            supabase.table("contacts")
            .select("email")
            .eq("lead_id", lead_id)
            .execute()
        )
        existing_emails = {
            c["email"].lower()
            for c in (existing_contacts.data or [])
            if c.get("email")
        }

        inserted = 0
        for result in results:
            if result.email.lower() in existing_emails:
                continue

            contact_data = {
                "lead_id": lead_id,
                "first_name": result.first_name,
                "last_name": result.last_name,
                "full_name": result.full_name or (
                    f"{result.first_name or ''} {result.last_name or ''}".strip() or None
                ),
                "designation": result.designation,
                "email": result.email,
                "email_confidence": result.email_confidence,
                "email_status": result.email_status,
            }

            supabase.table("contacts").insert(contact_data).execute()
            existing_emails.add(result.email.lower())
            inserted += 1

        # 5. Update lead status if ≥1 verified email
        has_verified = any(
            r.email_status == "verified" and r.email_confidence > 70
            for r in results
        )
        if has_verified:
            supabase.table("leads").update(
                {"status": "in_campaign"}
            ).eq("id", lead_id).execute()

        logger.info(
            "Email find complete for lead %s — %d found, %d new inserted",
            lead_id, len(results), inserted,
        )
        return {
            "status": "completed",
            "contacts_found": len(results),
            "contacts_inserted": inserted,
            "has_verified": has_verified,
        }

    except Exception as exc:
        logger.exception("Email finding failed for lead %s: %s", lead_id, exc)
        raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
#  Email-sending tasks
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    bind=True,
    name="email_tasks.send_queued_email",
    max_retries=2,
    default_retry_delay=60,
    queue="email",
)
def send_queued_email(self, email_log_id: str):
    """
    Send a single queued/approved email via Brevo SMTP.

    1. Fetch email_log — abort if status not sendable
    2. Mark 'sending' (optimistic lock)
    3. Send via BrevoEmailSender
    4. On success: advance_sequence + increment daily counter
    5. On failure: retry or mark 'failed'
    """
    try:
        result = send_campaign_email(email_log_id)

        if result.get("status") == "sent":
            # Advance sequence
            log = (
                supabase.table("email_logs")
                .select("campaign_lead_id")
                .eq("id", email_log_id)
                .single()
                .execute()
            ).data
            if log and log.get("campaign_lead_id"):
                from app.services.campaign_engine import CampaignEngine
                CampaignEngine().advance_sequence(log["campaign_lead_id"])

        return result

    except Exception as exc:
        logger.exception("send_queued_email failed for %s: %s", email_log_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(name="email_tasks.run_send_loop")
def run_send_loop():
    """
    Main scheduled task — runs every 15 minutes via Celery Beat.

    For each active campaign:
      - Check daily limit
      - Check send window (timezone-aware)
      - Get due campaign_leads
      - Build personalized emails
      - Queue or auto-send based on send_mode

    Safety rules:
      - Never send to same email twice in 24h
      - Never send if lead status = 'replied'
      - Bounce/unsubscribe handling
    """
    from app.services.campaign_engine import CampaignEngine
    import pytz

    engine = CampaignEngine()
    now_utc = datetime.now(timezone.utc)

    # 1. Get all active campaigns
    campaigns = (
        supabase.table("campaigns")
        .select("*")
        .eq("status", "active")
        .execute()
    ).data or []

    total_queued = 0
    total_sent = 0

    for campaign in campaigns:
        cid = campaign["id"]

        # 2a. Check daily limit
        if not daily_tracker.can_send(cid, campaign.get("daily_limit", 30)):
            logger.info("Campaign %s: daily limit reached (%d)", cid, campaign.get("daily_limit", 30))
            continue

        # 2b. Check send window (respect campaign timezone)
        tz_name = campaign.get("timezone", "UTC")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.utc
        local_now = now_utc.astimezone(tz)
        local_time = local_now.strftime("%H:%M")

        window_start = campaign.get("send_window_start", "09:00")
        window_end = campaign.get("send_window_end", "17:00")

        if not (window_start <= local_time <= window_end):
            logger.debug("Campaign %s: outside send window (%s not in %s-%s)", cid, local_time, window_start, window_end)
            continue

        # 2c. Get due campaign_lead_ids
        due_ids = engine.get_due_sends(cid)
        if not due_ids:
            continue

        remaining_quota = campaign.get("daily_limit", 30) - daily_tracker.get_sent_today(cid)

        for cl_id in due_ids:
            if remaining_quota <= 0:
                break

            # Fetch campaign_lead details
            cl = (
                supabase.table("campaign_leads")
                .select("current_step, campaign_id, lead_id, contact_id, status")
                .eq("id", cl_id)
                .single()
                .execute()
            ).data
            if not cl:
                continue

            # Safety: skip if lead has replied
            lead = (
                supabase.table("leads")
                .select("status")
                .eq("id", cl["lead_id"])
                .single()
                .execute()
            ).data
            if lead and lead.get("status") == "replied":
                continue

            # Safety: check contact hasn't been emailed in last 24h
            if cl.get("contact_id"):
                recent = (
                    supabase.table("email_logs")
                    .select("id")
                    .eq("contact_id", cl["contact_id"])
                    .eq("status", "sent")
                    .gte("sent_at", (now_utc - __import__("datetime").timedelta(hours=24)).isoformat())
                    .limit(1)
                    .execute()
                ).data
                if recent:
                    logger.debug("Skipping contact %s — already emailed in last 24h", cl["contact_id"])
                    continue

            next_step = cl["current_step"] + 1

            # Check if sequence step exists
            seq_check = (
                supabase.table("sequences")
                .select("id")
                .eq("campaign_id", cid)
                .eq("step_number", next_step)
                .limit(1)
                .execute()
            )
            if not seq_check.data:
                engine.advance_sequence(cl_id)
                continue

            # Build personalized email draft
            draft = engine.build_email_for_step(cl_id, next_step)
            if not draft:
                logger.warning("Could not build draft for campaign_lead %s step %d", cl_id, next_step)
                continue

            # Determine initial status based on send_mode
            send_mode = campaign.get("send_mode", "review")
            initial_status = "approved" if send_mode == "auto" else "queued"

            # Insert email_log
            email_data = {
                "campaign_lead_id": draft.campaign_lead_id,
                "contact_id": cl["contact_id"],
                "sequence_id": draft.sequence_id,
                "variant_sent": draft.variant,
                "subject": draft.subject,
                "body": draft.body,
                "status": initial_status,
                "tracking_id": draft.tracking_id,
            }

            log_result = supabase.table("email_logs").insert(email_data).execute()
            total_queued += 1

            if send_mode == "auto" and log_result.data:
                # Dispatch immediate send
                send_queued_email.delay(log_result.data[0]["id"])
                total_sent += 1
                remaining_quota -= 1

    logger.info("run_send_loop: %d queued, %d auto-dispatched across %d campaigns", total_queued, total_sent, len(campaigns))
    return {"campaigns_checked": len(campaigns), "queued": total_queued, "auto_dispatched": total_sent}


@celery_app.task(name="email_tasks.process_email_queue")
def process_email_queue(campaign_id: str = None, limit: int = 30):
    """Process approved emails in the queue — send them."""
    query = (
        supabase.table("email_logs")
        .select("id")
        .eq("status", "approved")
        .order("queued_at")
        .limit(limit)
    )

    # Filter by campaign if specified
    if campaign_id:
        cl_ids = (
            supabase.table("campaign_leads")
            .select("id")
            .eq("campaign_id", campaign_id)
            .execute()
        ).data or []
        if cl_ids:
            query = query.in_("campaign_lead_id", [c["id"] for c in cl_ids])

    result = query.execute()

    sent_count = 0
    for email_log in (result.data or []):
        send_result = send_campaign_email(email_log["id"])
        if send_result.get("status") == "sent":
            sent_count += 1

    return {"processed": len(result.data or []), "sent": sent_count}


@celery_app.task(name="email_tasks.advance_sequences")
def advance_sequences():
    """
    Periodic task: find all due campaign_leads and advance them.
    Now delegates to run_send_loop for the main pipeline.
    Kept for backward compat — calls run_send_loop internally.
    """
    return run_send_loop()


@celery_app.task(name="email_tasks.poll_replies_task")
def poll_replies_task():
    """
    Periodic task — runs every 10 minutes via Celery Beat.
    Polls the IMAP inbox for replies, matches them to sent emails,
    and processes sentiment classification + status updates.
    """
    from app.services.reply_tracker import ReplyPoller

    poller = ReplyPoller()
    replies = poller.poll_inbox()

    matched = 0
    unmatched = 0

    for reply in replies:
        email_log_id = poller.match_reply_to_log(reply)
        if email_log_id:
            result = poller.process_reply(reply, email_log_id)
            matched += 1
            logger.info(
                "Reply processed: from=%s sentiment=%s log=%s",
                reply.from_email,
                result.get("sentiment", "unknown"),
                email_log_id,
            )
        else:
            unmatched += 1
            logger.info(
                "Reply unmatched: from=%s subject=%s",
                reply.from_email,
                reply.subject[:50],
            )

    summary = {"polled": len(replies), "matched": matched, "unmatched": unmatched}
    logger.info("poll_replies_task complete: %s", summary)
    return summary
