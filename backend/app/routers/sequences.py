"""
Sequences API — CRUD for multi-step campaign email sequences.

Endpoints:
  GET    /campaigns/{campaign_id}/sequences   → list all steps
  POST   /campaigns/{campaign_id}/sequences   → add a step
  PATCH  /sequences/{sequence_id}             → update a step
  DELETE /sequences/{sequence_id}             → delete (draft campaigns only)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.database import supabase

router = APIRouter(tags=["Sequences"])


# ── Request models ─────────────────────────────────────────────────────────


class SequenceStepCreate(BaseModel):
    step_number: int
    step_name: Optional[str] = None
    delay_days: int = 0
    variant_a_subject: Optional[str] = None
    variant_a_body: Optional[str] = None
    variant_b_subject: Optional[str] = None
    variant_b_body: Optional[str] = None
    split_ratio: float = 0.5


class SequenceStepUpdate(BaseModel):
    step_number: Optional[int] = None
    step_name: Optional[str] = None
    delay_days: Optional[int] = None
    variant_a_subject: Optional[str] = None
    variant_a_body: Optional[str] = None
    variant_b_subject: Optional[str] = None
    variant_b_body: Optional[str] = None
    split_ratio: Optional[float] = None
    winner_variant: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/campaigns/{campaign_id}/sequences")
async def list_sequences(campaign_id: str):
    """Return all sequence steps for a campaign, ordered by step_number."""
    # Verify campaign exists
    campaign = (
        supabase.table("campaigns")
        .select("id")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not campaign.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = (
        supabase.table("sequences")
        .select("*")
        .eq("campaign_id", campaign_id)
        .order("step_number")
        .execute()
    )
    return result.data or []


@router.post("/campaigns/{campaign_id}/sequences", status_code=201)
async def create_sequence_step(campaign_id: str, body: SequenceStepCreate):
    """
    Add a new sequence step to a campaign.
    Validates that step_number isn't duplicated.
    """
    # Verify campaign exists
    campaign = (
        supabase.table("campaigns")
        .select("id, status")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not campaign.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check for duplicate step_number
    existing = (
        supabase.table("sequences")
        .select("id")
        .eq("campaign_id", campaign_id)
        .eq("step_number", body.step_number)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"Step {body.step_number} already exists for this campaign",
        )

    data = body.model_dump()
    data["campaign_id"] = campaign_id

    result = supabase.table("sequences").insert(data).execute()
    return result.data[0]


@router.get("/sequences/{sequence_id}")
async def get_sequence(sequence_id: str):
    """Get a single sequence step by ID."""
    result = (
        supabase.table("sequences")
        .select("*")
        .eq("id", sequence_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Sequence step not found")
    return result.data


@router.patch("/sequences/{sequence_id}")
async def update_sequence_step(sequence_id: str, body: SequenceStepUpdate):
    """Update any sequence step fields."""
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        supabase.table("sequences")
        .update(data)
        .eq("id", sequence_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Sequence step not found")
    return result.data[0]


@router.delete("/sequences/{sequence_id}")
async def delete_sequence_step(sequence_id: str):
    """
    Delete a sequence step.
    Only allowed if the parent campaign is in 'draft' status.
    """
    # Fetch sequence to get campaign_id
    seq = (
        supabase.table("sequences")
        .select("campaign_id")
        .eq("id", sequence_id)
        .single()
        .execute()
    )
    if not seq.data:
        raise HTTPException(status_code=404, detail="Sequence step not found")

    # Check campaign status
    campaign = (
        supabase.table("campaigns")
        .select("status")
        .eq("id", seq.data["campaign_id"])
        .single()
        .execute()
    )
    if campaign.data and campaign.data["status"] != "draft":
        raise HTTPException(
            status_code=403,
            detail="Cannot delete sequence steps from a non-draft campaign",
        )

    supabase.table("sequences").delete().eq("id", sequence_id).execute()
    return {"detail": "Sequence step deleted"}
