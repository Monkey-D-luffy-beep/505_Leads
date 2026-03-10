"""
Signal & scoring API endpoints.

- Signal definitions CRUD (Tier 1-3)
- Per-lead signal listing, manual signal add, rescore
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import asyncio

from app.database import supabase
from app.services.scorer import score_lead

router = APIRouter(tags=["Signals"])


# ── Request models ─────────────────────────────────────────────────────────


class SignalDefinitionCreate(BaseModel):
    signal_key: str
    label: str
    description: Optional[str] = None
    default_weight: int = 10
    detection_type: str = "custom"
    detection_logic: dict = {}


class SignalDefinitionUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    default_weight: Optional[int] = None
    is_active: Optional[bool] = None
    detection_logic: Optional[dict] = None


class ManualSignalAdd(BaseModel):
    signal_key: str
    signal_value: str = ""


# ═══════════════════════════════════════════════════════════════════════════
#  Signal Definitions CRUD
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/signals/definitions")
async def list_signal_definitions():
    """Return all signal definitions ordered by tier then label."""
    result = (
        supabase.table("signal_definitions")
        .select("*")
        .order("tier")
        .order("label")
        .execute()
    )
    return result.data


@router.post("/signals/definitions", status_code=201)
async def create_signal_definition(defn: SignalDefinitionCreate):
    """
    Create a Tier 3 (custom) signal definition.
    Tier is automatically set to 3.
    """
    data = defn.model_dump()
    data["tier"] = 3  # user-created signals are always Tier 3

    # Check for duplicate key
    existing = (
        supabase.table("signal_definitions")
        .select("id")
        .eq("signal_key", data["signal_key"])
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Signal key already exists")

    result = supabase.table("signal_definitions").insert(data).execute()
    return result.data[0]


@router.patch("/signals/definitions/{signal_key}")
async def update_signal_definition(signal_key: str, update: SignalDefinitionUpdate):
    """Update weight, label, description, or active status of a definition."""
    data = update.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        supabase.table("signal_definitions")
        .update(data)
        .eq("signal_key", signal_key)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Signal definition not found")
    return result.data[0]


@router.delete("/signals/definitions/{signal_key}", status_code=200)
async def delete_signal_definition(signal_key: str):
    """
    Delete a signal definition.
    Only Tier 3 (custom) signals may be deleted.
    """
    # Check tier
    defn = (
        supabase.table("signal_definitions")
        .select("tier")
        .eq("signal_key", signal_key)
        .single()
        .execute()
    )
    if not defn.data:
        raise HTTPException(status_code=404, detail="Signal definition not found")
    if defn.data.get("tier") in (1, 2):
        raise HTTPException(
            status_code=403,
            detail="Cannot delete built-in Tier 1/2 signal definitions",
        )

    supabase.table("signal_definitions").delete().eq("signal_key", signal_key).execute()
    return {"detail": f"Signal '{signal_key}' deleted"}


# ═══════════════════════════════════════════════════════════════════════════
#  Per-lead signal endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/leads/{lead_id}/signals")
async def get_lead_signals(lead_id: str):
    """
    Return all detected signals for a lead, joined with their
    definition weights for context.
    """
    signals = (
        supabase.table("signals")
        .select("*")
        .eq("lead_id", lead_id)
        .order("detected_at", desc=True)
        .execute()
    )
    if not signals.data:
        return []

    # Enrich with definition info
    defs = supabase.table("signal_definitions").select("*").execute()
    defs_map = {d["signal_key"]: d for d in (defs.data or [])}

    enriched = []
    for s in signals.data:
        defn = defs_map.get(s["signal_key"], {})
        enriched.append({
            **s,
            "label": defn.get("label", s["signal_key"]),
            "tier": defn.get("tier"),
            "default_weight": defn.get("default_weight", 0),
            "description": defn.get("description"),
        })

    return enriched


@router.post("/leads/{lead_id}/signals/manual", status_code=201)
async def add_manual_signal(lead_id: str, body: ManualSignalAdd):
    """
    Manually add a signal to a lead (usually Tier 3 custom signals).
    """
    # Verify lead exists
    lead = (
        supabase.table("leads")
        .select("id")
        .eq("id", lead_id)
        .single()
        .execute()
    )
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Verify signal definition exists
    defn = (
        supabase.table("signal_definitions")
        .select("default_weight")
        .eq("signal_key", body.signal_key)
        .single()
        .execute()
    )
    if not defn.data:
        raise HTTPException(status_code=404, detail="Signal definition not found")

    signal_data = {
        "lead_id": lead_id,
        "signal_key": body.signal_key,
        "signal_value": body.signal_value,
        "signal_score": defn.data["default_weight"],
    }

    result = supabase.table("signals").insert(signal_data).execute()
    return result.data[0]


@router.post("/leads/{lead_id}/rescore")
async def rescore_lead(lead_id: str, campaign_id: Optional[str] = Query(None)):
    """
    Re-run scoring for a lead using current signals and weights.
    Useful after signal weight changes or manual signal additions.
    """
    # Verify lead exists
    lead = (
        supabase.table("leads")
        .select("id")
        .eq("id", lead_id)
        .single()
        .execute()
    )
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")

    result = await score_lead(lead_id, campaign_id)
    return result
