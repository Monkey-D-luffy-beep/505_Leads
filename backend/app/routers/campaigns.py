"""
Campaigns API — CRUD, enrollment, pause/resume, lead listing with stats.

Endpoints:
  GET    /campaigns                     → list all with summary stats
  POST   /campaigns                     → create new campaign
  PATCH  /campaigns/{id}                → update (auto-enroll on activate)
  DELETE /campaigns/{id}                → soft delete (status → 'complete')
  POST   /campaigns/{id}/enroll         → manually trigger enrollment
  POST   /campaigns/{id}/pause          → pause a campaign
  POST   /campaigns/{id}/resume         → resume a campaign
  GET    /campaigns/{id}/leads          → paginated campaign_leads
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from app.database import supabase
from app.services.campaign_engine import CampaignEngine

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

engine = CampaignEngine()


# ── Request models ─────────────────────────────────────────────────────────


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_filters: dict = {}
    min_score: int = 30
    signal_weights: dict = {}
    send_mode: str = "review"
    daily_limit: int = 30
    send_window_start: str = "09:00"
    send_window_end: str = "17:00"
    timezone: str = "UTC"


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_filters: Optional[dict] = None
    min_score: Optional[int] = None
    signal_weights: Optional[dict] = None
    status: Optional[str] = None
    send_mode: Optional[str] = None
    daily_limit: Optional[int] = None
    send_window_start: Optional[str] = None
    send_window_end: Optional[str] = None
    timezone: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/")
async def list_campaigns(status: Optional[str] = None):
    """
    Return all campaigns with summary stats:
      enrolled count, sent count, reply count, status.
    """
    query = supabase.table("campaigns").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    result = query.execute()

    campaigns = result.data or []
    enriched = []
    for c in campaigns:
        cid = c["id"]

        # Enrolled count
        enrolled = (
            supabase.table("campaign_leads")
            .select("id", count="exact")
            .eq("campaign_id", cid)
            .execute()
        )
        # Sent count
        sent = (
            supabase.table("email_logs")
            .select("id", count="exact")
            .eq("status", "sent")
            .in_(
                "campaign_lead_id",
                [
                    row["id"]
                    for row in (
                        supabase.table("campaign_leads")
                        .select("id")
                        .eq("campaign_id", cid)
                        .execute()
                    ).data or []
                ],
            )
            .execute()
            if (
                supabase.table("campaign_leads")
                .select("id")
                .eq("campaign_id", cid)
                .execute()
            ).data
            else type("R", (), {"count": 0})()
        )
        # Reply count
        replied = (
            supabase.table("campaign_leads")
            .select("id", count="exact")
            .eq("campaign_id", cid)
            .eq("status", "replied")
            .execute()
        )

        enriched.append({
            **c,
            "enrolled_count": enrolled.count or 0,
            "sent_count": getattr(sent, "count", 0) or 0,
            "reply_count": replied.count or 0,
        })

    return enriched


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get a single campaign by ID."""
    result = (
        supabase.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result.data


@router.post("/", status_code=201)
async def create_campaign(body: CampaignCreate):
    """Create a new campaign (always starts in 'draft' status)."""
    data = body.model_dump()
    data["status"] = "draft"
    result = supabase.table("campaigns").insert(data).execute()
    return result.data[0]


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: str, body: CampaignUpdate):
    """
    Update campaign fields.
    If status changes to 'active' from 'draft':
      - Verify at least one sequence step exists
      - Auto-trigger lead enrollment
    """
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Check current campaign
    current = (
        supabase.table("campaigns")
        .select("status")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Activating from draft — validate sequences exist
    new_status = data.get("status")
    if new_status == "active" and current.data["status"] == "draft":
        sequences = (
            supabase.table("sequences")
            .select("id")
            .eq("campaign_id", campaign_id)
            .execute()
        )
        if not sequences.data:
            raise HTTPException(
                status_code=422,
                detail="Cannot activate campaign with no sequences. Add at least one step.",
            )

    result = (
        supabase.table("campaigns")
        .update(data)
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Auto-enroll on activation
    if new_status == "active" and current.data["status"] == "draft":
        enrollment = engine.enroll_leads(campaign_id)
        return {**result.data[0], "enrollment_summary": enrollment}

    return result.data[0]


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Soft delete — set status to 'complete', leave logs intact."""
    result = (
        supabase.table("campaigns")
        .update({"status": "complete"})
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"detail": "Campaign archived (status set to complete)"}


@router.post("/{campaign_id}/enroll")
async def enroll_leads(campaign_id: str):
    """Manually trigger lead enrollment for a campaign."""
    # Verify campaign exists and is active
    campaign = (
        supabase.table("campaigns")
        .select("status")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not campaign.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.data["status"] not in ("active", "draft"):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot enroll leads — campaign status is '{campaign.data['status']}'",
        )

    result = engine.enroll_leads(campaign_id)
    return result


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    """Pause a campaign — no emails will be sent."""
    result = (
        supabase.table("campaigns")
        .update({"status": "paused"})
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"detail": "Campaign paused", "campaign": result.data[0]}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    """Resume a paused campaign back to active."""
    current = (
        supabase.table("campaigns")
        .select("status")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if current.data["status"] != "paused":
        raise HTTPException(
            status_code=422,
            detail="Only paused campaigns can be resumed",
        )

    result = (
        supabase.table("campaigns")
        .update({"status": "active"})
        .eq("id", campaign_id)
        .execute()
    )
    return {"detail": "Campaign resumed", "campaign": result.data[0]}


@router.get("/{campaign_id}/leads")
async def list_campaign_leads(
    campaign_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = None,
):
    """
    Return paginated campaign_leads with joined lead + contact info.
    """
    offset = (page - 1) * per_page

    query = (
        supabase.table("campaign_leads")
        .select("*, leads(*), contacts(*)")
        .eq("campaign_id", campaign_id)
        .order("enrolled_at", desc=True)
    )
    if status:
        query = query.eq("status", status)

    result = query.range(offset, offset + per_page - 1).execute()
    return {
        "page": page,
        "per_page": per_page,
        "data": result.data or [],
    }
