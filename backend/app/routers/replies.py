"""
Replies Router — inbox management for received replies.

Endpoints:
  GET    /replies              → list replies (filterable, paginated)
  GET    /replies/unread-count → unread badge count
  GET    /replies/{reply_id}   → full reply with email thread context
  POST   /replies/{reply_id}/mark-read      → mark single reply as read
  POST   /replies/mark-all-read             → mark all unread replies as read
  PATCH  /replies/{reply_id}/sentiment      → manually override sentiment
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.database import supabase

router = APIRouter(prefix="/replies", tags=["Replies"])


# ── Request Models ─────────────────────────────────────────────────────────


class SentimentOverride(BaseModel):
    sentiment: str  # positive | negative | neutral | out-of-office | unsubscribe


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/unread-count")
async def unread_count():
    """
    Return count of unread replies — used for dashboard notification badge.
    Defined BEFORE /{reply_id} to avoid route-param collision.
    """
    result = (
        supabase.table("replies")
        .select("id", count="exact")
        .eq("is_read", False)
        .execute()
    )
    return {"count": result.count or 0}


@router.get("/")
async def list_replies(
    sentiment: Optional[str] = None,
    is_read: Optional[bool] = None,
    campaign_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """
    List all replies ordered by received_at DESC.
    Includes joined lead and contact info.
    """
    offset = (page - 1) * per_page

    query = (
        supabase.table("replies")
        .select("*, email_logs(*, campaign_leads(*, leads(*)), contacts(*))")
        .order("received_at", desc=True)
    )

    if sentiment:
        query = query.eq("sentiment", sentiment)

    if is_read is not None:
        query = query.eq("is_read", is_read)

    # Filter by campaign_id through the join chain
    if campaign_id:
        # Get campaign_lead IDs for this campaign
        cl_ids_resp = (
            supabase.table("campaign_leads")
            .select("id")
            .eq("campaign_id", campaign_id)
            .execute()
        )
        cl_ids = [row["id"] for row in (cl_ids_resp.data or [])]
        if cl_ids:
            # Get email_log IDs for those campaign_leads
            el_ids_resp = (
                supabase.table("email_logs")
                .select("id")
                .in_("campaign_lead_id", cl_ids)
                .execute()
            )
            el_ids = [row["id"] for row in (el_ids_resp.data or [])]
            if el_ids:
                query = query.in_("email_log_id", el_ids)
            else:
                return {"page": page, "per_page": per_page, "total": 0, "data": []}
        else:
            return {"page": page, "per_page": per_page, "total": 0, "data": []}

    result = query.range(offset, offset + per_page - 1).execute()

    return {
        "page": page,
        "per_page": per_page,
        "data": result.data or [],
    }


@router.get("/{reply_id}")
async def get_reply(reply_id: str):
    """
    Full reply detail with email thread context.
    Returns the reply + all prior email_logs sent to the same contact.
    """
    # Fetch the reply with joined data
    reply = (
        supabase.table("replies")
        .select("*, email_logs(*, campaign_leads(*, leads(*), campaigns(*)))")
        .eq("id", reply_id)
        .single()
        .execute()
    )
    if not reply.data:
        raise HTTPException(status_code=404, detail="Reply not found")

    reply_data = reply.data

    # Build email thread — all sends to the same contact
    thread = []
    contact_id = reply_data.get("contact_id")
    if contact_id:
        thread_result = (
            supabase.table("email_logs")
            .select("id, subject, body, status, variant_sent, sent_at, opened_at, clicked_at, replied_at")
            .eq("contact_id", contact_id)
            .order("sent_at")
            .execute()
        )
        thread = thread_result.data or []

    reply_data["thread"] = thread
    return reply_data


@router.post("/{reply_id}/mark-read")
async def mark_read(reply_id: str):
    """Mark a single reply as read."""
    result = (
        supabase.table("replies")
        .update({"is_read": True})
        .eq("id", reply_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reply not found")
    return {"status": "marked_read"}


@router.post("/mark-all-read")
async def mark_all_read():
    """Mark ALL unread replies as read."""
    supabase.table("replies").update(
        {"is_read": True}
    ).eq("is_read", False).execute()
    return {"status": "all_marked_read"}


@router.patch("/{reply_id}/sentiment")
async def override_sentiment(reply_id: str, body: SentimentOverride):
    """
    Manually override the sentiment classification for a reply.
    Valid values: positive, negative, neutral, out-of-office, unsubscribe
    """
    valid = {"positive", "negative", "neutral", "out-of-office", "unsubscribe"}
    if body.sentiment not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sentiment. Must be one of: {', '.join(sorted(valid))}",
        )

    result = (
        supabase.table("replies")
        .update({"sentiment": body.sentiment})
        .eq("id", reply_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reply not found")

    return result.data[0]
