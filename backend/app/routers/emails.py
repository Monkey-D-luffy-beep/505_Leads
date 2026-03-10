"""
Emails API — email log listing + tracking pixel/click endpoints.

Endpoints:
  GET    /emails                       → list email logs (filterable)
  GET    /emails/{id}                  → single email log
  GET    /track/open/{tracking_id}     → tracking pixel (1x1 GIF)
  GET    /track/click/{tracking_id}    → click redirect + log
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, RedirectResponse
from typing import Optional

from app.database import supabase

router = APIRouter(tags=["Emails"])

# 1x1 transparent GIF bytes
TRACKING_PIXEL = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
    b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00'
    b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
    b'\x44\x01\x00\x3b'
)


# ═══════════════════════════════════════════════════════════════════════════
#  Email log listing
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/emails")
async def list_emails(
    status: Optional[str] = None,
    campaign_lead_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List email logs with optional filters and pagination."""
    offset = (page - 1) * per_page

    query = supabase.table("email_logs").select("*").order("queued_at", desc=True)
    if status:
        query = query.eq("status", status)
    if campaign_lead_id:
        query = query.eq("campaign_lead_id", campaign_lead_id)

    result = query.range(offset, offset + per_page - 1).execute()
    return {
        "page": page,
        "per_page": per_page,
        "data": result.data or [],
    }


@router.get("/emails/{email_id}")
async def get_email(email_id: str):
    """Get a single email log by ID with full details."""
    result = (
        supabase.table("email_logs")
        .select("*")
        .eq("id", email_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Email log not found")
    return result.data


# ═══════════════════════════════════════════════════════════════════════════
#  Tracking endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/track/open/{tracking_id}")
async def track_open(tracking_id: str):
    """
    Tracking pixel endpoint — called when email is opened.
    Sets opened_at (first open only) and returns a 1x1 transparent GIF.
    """
    log = (
        supabase.table("email_logs")
        .select("id, opened_at, status")
        .eq("tracking_id", tracking_id)
        .limit(1)
        .execute()
    )

    if log.data:
        record = log.data[0]
        if not record.get("opened_at"):
            now = datetime.now(timezone.utc).isoformat()
            update_data = {"opened_at": now}
            if record.get("status") in ("sent", "approved"):
                update_data["status"] = "opened"
            supabase.table("email_logs").update(update_data).eq("id", record["id"]).execute()

    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/track/click/{tracking_id}")
async def track_click(tracking_id: str, url: str = Query(...)):
    """
    Click tracking endpoint — logs click event and redirects to actual URL.
    """
    log = (
        supabase.table("email_logs")
        .select("id, clicked_at, status")
        .eq("tracking_id", tracking_id)
        .limit(1)
        .execute()
    )

    if log.data:
        record = log.data[0]
        if not record.get("clicked_at"):
            now = datetime.now(timezone.utc).isoformat()
            update_data = {"clicked_at": now}
            if record.get("status") not in ("replied",):
                update_data["status"] = "clicked"
            supabase.table("email_logs").update(update_data).eq("id", record["id"]).execute()

    return RedirectResponse(url=url, status_code=302)
