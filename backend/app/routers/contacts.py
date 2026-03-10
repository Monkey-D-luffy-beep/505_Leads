"""
Contacts API — find, list, create, update, delete contacts for leads.

Endpoints:
  POST   /leads/{lead_id}/find-emails       → trigger email finding task
  GET    /leads/{lead_id}/contacts           → list contacts for a lead
  POST   /leads/{lead_id}/contacts           → manually add a contact
  PATCH  /contacts/{contact_id}              → update contact fields
  DELETE /contacts/{contact_id}              → hard delete
  POST   /leads/find-emails/bulk             → bulk email finding
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from app.database import supabase

router = APIRouter(tags=["Contacts"])


# ── Request models ─────────────────────────────────────────────────────────


class ManualContactCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    designation: Optional[str] = None
    email: str
    linkedin_url: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    email_status: Optional[str] = None


class BulkFindRequest(BaseModel):
    lead_ids: List[str]


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/leads/{lead_id}/find-emails")
async def trigger_find_emails(lead_id: str):
    """
    Trigger async Celery task to find emails for a lead using
    all three strategies (Hunter.io → scraped → permutation).
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

    from app.workers.email_tasks import find_emails_for_lead

    task = find_emails_for_lead.delay(lead_id)
    return {"job_id": task.id, "status": "started"}


@router.get("/leads/{lead_id}/contacts")
async def list_contacts(lead_id: str):
    """Return all contacts for a lead, ordered by confidence desc."""
    result = (
        supabase.table("contacts")
        .select("*")
        .eq("lead_id", lead_id)
        .order("email_confidence", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/leads/{lead_id}/contacts", status_code=201)
async def create_contact(lead_id: str, body: ManualContactCreate):
    """Manually add a contact to a lead."""
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

    # Check for duplicate email on same lead
    existing = (
        supabase.table("contacts")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("email", body.email)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Contact with this email already exists for this lead",
        )

    contact_data = {
        "lead_id": lead_id,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "full_name": (
            f"{body.first_name or ''} {body.last_name or ''}".strip() or None
        ),
        "designation": body.designation,
        "email": body.email,
        "linkedin_url": body.linkedin_url,
        "email_confidence": 100,   # manual = full confidence
        "email_status": "verified",
    }

    result = supabase.table("contacts").insert(contact_data).execute()
    return result.data[0]


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate):
    """Update allowed contact fields."""
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate email_status if provided
    valid_statuses = {"unverified", "verified", "bounced", "invalid"}
    if "email_status" in data and data["email_status"] not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"email_status must be one of: {', '.join(sorted(valid_statuses))}",
        )

    # Rebuild full_name if first/last name changed
    if "first_name" in data or "last_name" in data:
        # Fetch current values for the fields not being updated
        current = (
            supabase.table("contacts")
            .select("first_name, last_name")
            .eq("id", contact_id)
            .single()
            .execute()
        )
        if current.data:
            fn = data.get("first_name", current.data.get("first_name")) or ""
            ln = data.get("last_name", current.data.get("last_name")) or ""
            data["full_name"] = f"{fn} {ln}".strip() or None

    result = (
        supabase.table("contacts")
        .update(data)
        .eq("id", contact_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    return result.data[0]


@router.delete("/contacts/{contact_id}", status_code=200)
async def delete_contact(contact_id: str):
    """Hard delete a contact record."""
    result = (
        supabase.table("contacts")
        .delete()
        .eq("id", contact_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"detail": "Contact deleted"}


@router.post("/leads/find-emails/bulk")
async def bulk_find_emails(body: BulkFindRequest):
    """
    Dispatch email finding tasks for multiple leads at once.
    Returns the count of dispatched jobs.
    """
    if not body.lead_ids:
        raise HTTPException(status_code=400, detail="lead_ids list is empty")

    from app.workers.email_tasks import find_emails_for_lead

    dispatched = 0
    for lead_id in body.lead_ids:
        find_emails_for_lead.delay(lead_id)
        dispatched += 1

    return {"dispatched": dispatched, "status": "started"}
