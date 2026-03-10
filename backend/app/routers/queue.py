"""
Review Queue API — human-approval workflow for emails in review mode.

Endpoints:
  GET    /queue                           → list queued emails
  GET    /queue/{email_log_id}            → preview a queued email
  POST   /queue/{email_log_id}/approve    → approve and dispatch
  POST   /queue/{email_log_id}/skip       → skip (still advance sequence)
  PATCH  /queue/{email_log_id}/edit       → edit subject/body before approval
  POST   /queue/bulk-approve              → approve multiple at once
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from app.database import supabase

router = APIRouter(prefix="/queue", tags=["Queue"])


# ── Request models ─────────────────────────────────────────────────────────


class EmailEdit(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class BulkApproveRequest(BaseModel):
    email_log_ids: List[str]


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/")
async def list_queue(
    campaign_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """
    Return queued email_logs with joined lead and contact data.
    Ordered by queued_at ASC (oldest first).
    """
    offset = (page - 1) * per_page

    # Build query — join through campaign_leads to get lead/contact
    query = (
        supabase.table("email_logs")
        .select("*, campaign_leads(*, leads(*), contacts(*))")
        .eq("status", "queued")
        .order("queued_at")
    )

    if campaign_id:
        # Filter by campaign_id through the campaign_leads join
        cl_ids_resp = (
            supabase.table("campaign_leads")
            .select("id")
            .eq("campaign_id", campaign_id)
            .execute()
        )
        cl_ids = [row["id"] for row in (cl_ids_resp.data or [])]
        if cl_ids:
            query = query.in_("campaign_lead_id", cl_ids)
        else:
            return {"page": page, "per_page": per_page, "data": []}

    result = query.range(offset, offset + per_page - 1).execute()
    return {
        "page": page,
        "per_page": per_page,
        "data": result.data or [],
    }


@router.get("/{email_log_id}")
async def preview_email(email_log_id: str):
    """Return full email preview with subject and rendered body."""
    result = (
        supabase.table("email_logs")
        .select("*, campaign_leads(*, leads(*), contacts(*))")
        .eq("id", email_log_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Email log not found")
    return result.data


@router.post("/{email_log_id}/approve")
async def approve_email(email_log_id: str):
    """
    Approve a queued email and dispatch it for sending.
    """
    # Verify it's in 'queued' status
    log = (
        supabase.table("email_logs")
        .select("id, status")
        .eq("id", email_log_id)
        .single()
        .execute()
    )
    if not log.data:
        raise HTTPException(status_code=404, detail="Email log not found")
    if log.data["status"] != "queued":
        raise HTTPException(
            status_code=422,
            detail=f"Email is '{log.data['status']}', not 'queued'",
        )

    # Set status to approved
    supabase.table("email_logs").update(
        {"status": "approved"}
    ).eq("id", email_log_id).execute()

    # Dispatch send task
    from app.workers.email_tasks import send_queued_email
    send_queued_email.delay(email_log_id)

    return {"status": "approved", "dispatched": True}


@router.post("/{email_log_id}/skip")
async def skip_email(email_log_id: str):
    """
    Skip a queued email. Still advances the sequence so the
    next step isn't blocked.
    """
    log = (
        supabase.table("email_logs")
        .select("id, status, campaign_lead_id")
        .eq("id", email_log_id)
        .single()
        .execute()
    )
    if not log.data:
        raise HTTPException(status_code=404, detail="Email log not found")
    if log.data["status"] != "queued":
        raise HTTPException(
            status_code=422,
            detail=f"Email is '{log.data['status']}', not 'queued'",
        )

    supabase.table("email_logs").update(
        {"status": "skipped"}
    ).eq("id", email_log_id).execute()

    # Advance sequence so next step isn't blocked
    if log.data.get("campaign_lead_id"):
        from app.services.campaign_engine import CampaignEngine
        CampaignEngine().advance_sequence(log.data["campaign_lead_id"])

    return {"status": "skipped"}


@router.patch("/{email_log_id}/edit")
async def edit_queued_email(email_log_id: str, body: EmailEdit):
    """
    Edit subject and/or body of a queued email before approval.
    Resets status back to 'queued' after edit.
    """
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Verify it exists and is editable
    log = (
        supabase.table("email_logs")
        .select("id, status")
        .eq("id", email_log_id)
        .single()
        .execute()
    )
    if not log.data:
        raise HTTPException(status_code=404, detail="Email log not found")
    if log.data["status"] not in ("queued",):
        raise HTTPException(
            status_code=422,
            detail=f"Can only edit emails in 'queued' status (current: '{log.data['status']}')",
        )

    data["status"] = "queued"  # ensure it stays queued after edit
    result = (
        supabase.table("email_logs")
        .update(data)
        .eq("id", email_log_id)
        .execute()
    )
    return result.data[0] if result.data else {"detail": "Updated"}


@router.post("/bulk-approve")
async def bulk_approve(body: BulkApproveRequest):
    """
    Approve and dispatch multiple queued emails at once.
    Returns count of successfully approved emails.
    """
    if not body.email_log_ids:
        raise HTTPException(status_code=400, detail="email_log_ids list is empty")

    from app.workers.email_tasks import send_queued_email

    approved = 0
    for log_id in body.email_log_ids:
        # Only approve if currently queued
        result = (
            supabase.table("email_logs")
            .update({"status": "approved"})
            .eq("id", log_id)
            .eq("status", "queued")
            .execute()
        )
        if result.data:
            send_queued_email.delay(log_id)
            approved += 1

    return {"approved": approved, "total_requested": len(body.email_log_ids)}
