from fastapi import APIRouter, Query, Depends
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
from app.database import supabase
from app.auth import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def get_overview(user: dict = Depends(get_current_user)):
    """Get high-level stats across all campaigns."""
    uid = user["sub"]
    leads = supabase.table("leads").select("id", count="exact").eq("user_id", uid).execute()
    campaigns = supabase.table("campaigns").select("id", count="exact").eq("user_id", uid).execute()
    active_campaigns = (
        supabase.table("campaigns")
        .select("id", count="exact")
        .eq("user_id", uid)
        .eq("status", "active")
        .execute()
    )
    emails_sent = (
        supabase.table("email_logs")
        .select("id", count="exact")
        .eq("status", "sent")
        .execute()
    )
    emails_opened = (
        supabase.table("email_logs")
        .select("id", count="exact")
        .eq("status", "opened")
        .execute()
    )

    # Emails sent in last 7 days
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    emails_sent_week = (
        supabase.table("email_logs")
        .select("id", count="exact")
        .eq("status", "sent")
        .gte("sent_at", week_ago)
        .execute()
    )

    replies = supabase.table("replies").select("id", count="exact").execute()
    queue_pending = (
        supabase.table("email_logs")
        .select("id", count="exact")
        .eq("status", "queued")
        .execute()
    )

    return {
        "total_leads": leads.count or 0,
        "total_campaigns": campaigns.count or 0,
        "active_campaigns": active_campaigns.count or 0,
        "emails_sent": emails_sent.count or 0,
        "emails_sent_week": emails_sent_week.count or 0,
        "emails_opened": emails_opened.count or 0,
        "total_replies": replies.count or 0,
        "queue_pending": queue_pending.count or 0,
    }


@router.get("/emails-over-time")
async def get_emails_over_time(
    days: int = Query(30, ge=1, le=90),
    campaign_id: Optional[str] = Query(None),
):
    """Get daily email counts for the last N days."""
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

    if campaign_id:
        # Get campaign_lead_ids for this campaign
        cl = supabase.table("campaign_leads").select("id").eq("campaign_id", campaign_id).execute()
        cl_ids = [r["id"] for r in (cl.data or [])]
        if not cl_ids:
            return {"data": []}
        query = (
            supabase.table("email_logs")
            .select("sent_at, status, opened_at")
            .in_("campaign_lead_id", cl_ids)
            .gte("sent_at", start_date)
            .order("sent_at")
        )
    else:
        query = (
            supabase.table("email_logs")
            .select("sent_at, status, opened_at")
            .gte("sent_at", start_date)
            .order("sent_at")
        )
    result = query.execute()

    sent_by_day = defaultdict(int)
    opened_by_day = defaultdict(int)

    for row in result.data or []:
        if row.get("sent_at"):
            day = row["sent_at"][:10]
            sent_by_day[day] += 1
        if row.get("opened_at"):
            day = row["opened_at"][:10]
            opened_by_day[day] += 1

    all_days = set(sent_by_day.keys()) | set(opened_by_day.keys())
    data = sorted(
        [{"date": d, "sent": sent_by_day.get(d, 0), "opened": opened_by_day.get(d, 0)} for d in all_days],
        key=lambda x: x["date"],
    )
    return {"data": data}


@router.get("/ab-results")
async def get_ab_results(campaign_id: Optional[str] = Query(None)):
    """Get A/B test performance per campaign step and variant."""
    # email_logs has no campaign_id; join via campaign_lead_id → campaign_leads
    query = supabase.table("email_logs").select(
        "campaign_lead_id, sequence_id, variant_sent, status, opened_at, campaign_leads(campaign_id), sequences(step_number)"
    )
    if campaign_id:
        cl = supabase.table("campaign_leads").select("id").eq("campaign_id", campaign_id).execute()
        cl_ids = [r["id"] for r in (cl.data or [])]
        if not cl_ids:
            return {"data": []}
        query = query.in_("campaign_lead_id", cl_ids)
    result = query.execute()

    buckets = defaultdict(lambda: {"sent": 0, "opens": 0, "replies": 0})

    for row in result.data or []:
        cid = (row.get("campaign_leads") or {}).get("campaign_id", "")
        step = (row.get("sequences") or {}).get("step_number", 1)
        variant = row.get("variant_sent", "a")
        key = (cid, step, variant)
        buckets[key]["sent"] += 1
        if row.get("opened_at"):
            buckets[key]["opens"] += 1
        if row.get("status") == "replied":
            buckets[key]["replies"] += 1

    data = []
    for (cid, step, variant), counts in sorted(buckets.items()):
        data.append({
            "campaign_id": cid,
            "step_number": step,
            "variant": variant,
            **counts,
        })
    return {"data": data}


@router.get("/sentiment-breakdown")
async def get_sentiment_breakdown(campaign_id: Optional[str] = Query(None)):
    """Get reply sentiment distribution."""
    if campaign_id:
        # replies has no campaign_id — join via email_log_id → email_logs → campaign_lead_id → campaign_leads
        cl = supabase.table("campaign_leads").select("id").eq("campaign_id", campaign_id).execute()
        cl_ids = [r["id"] for r in (cl.data or [])]
        if not cl_ids:
            return {"data": []}
        el = supabase.table("email_logs").select("id").in_("campaign_lead_id", cl_ids).execute()
        el_ids = [r["id"] for r in (el.data or [])]
        if not el_ids:
            return {"data": []}
        query = supabase.table("replies").select("sentiment").in_("email_log_id", el_ids)
    else:
        query = supabase.table("replies").select("sentiment")
    result = query.execute()

    counts = defaultdict(int)
    for row in result.data or []:
        sentiment = row.get("sentiment", "neutral")
        counts[sentiment] += 1

    data = [{"sentiment": s, "count": c} for s, c in sorted(counts.items())]
    return {"data": data}


@router.get("/campaign/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    """Get stats for a specific campaign."""
    campaign_leads = (
        supabase.table("campaign_leads")
        .select("id", count="exact")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    email_logs = (
        supabase.table("email_logs")
        .select("*, campaign_leads!inner(campaign_id)")
        .eq("campaign_leads.campaign_id", campaign_id)
        .execute()
    )

    sent = sum(1 for e in email_logs.data if e.get("status") == "sent")
    opened = sum(1 for e in email_logs.data if e.get("status") == "opened")
    replied = sum(1 for e in email_logs.data if e.get("status") == "replied")
    bounced = sum(1 for e in email_logs.data if e.get("status") == "bounced")

    return {
        "enrolled_leads": campaign_leads.count or 0,
        "emails_sent": sent,
        "emails_opened": opened,
        "emails_replied": replied,
        "emails_bounced": bounced,
        "open_rate": round(opened / sent * 100, 1) if sent else 0,
        "reply_rate": round(replied / sent * 100, 1) if sent else 0,
    }
