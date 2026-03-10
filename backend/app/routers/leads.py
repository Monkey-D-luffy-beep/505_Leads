from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
from pydantic import BaseModel
import uuid
import asyncio
import json
import logging

from app.database import supabase
from app.models.lead import LeadCreate, LeadUpdate, LeadResponse
from app.services.scraper import GoogleMapsScraper, scrape_website_meta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["Leads"])


# ── Request / Response models for scrape endpoints ─────────────────────────


class ScrapeRequest(BaseModel):
    keyword: str
    location: str
    max_results: int = 50


class BatchScrapeRequest(BaseModel):
    queries: List[ScrapeRequest]


class ScrapeJobResponse(BaseModel):
    job_id: str
    status: str


class ScrapeStatusResponse(BaseModel):
    job_id: str
    keyword: Optional[str] = None
    location: Optional[str] = None
    status: str
    total_found: int = 0
    processed: int = 0
    inserted: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
#  Scrape endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/scrape", response_model=ScrapeJobResponse)
async def trigger_scrape(req: ScrapeRequest):
    """
    Kick off a Google Maps scrape job.
    Tries Celery first; falls back to sync if Redis unavailable.
    """
    job_id = str(uuid.uuid4())
    try:
        from app.workers.scrape_tasks import run_scrape_job
        run_scrape_job.delay(
            keyword=req.keyword,
            location=req.location,
            max_results=req.max_results,
            job_id=job_id,
        )
        return ScrapeJobResponse(job_id=job_id, status="started")
    except Exception as e:
        logger.warning("Celery unavailable (%s), use /scrape-sync instead", e)
        raise HTTPException(
            status_code=503,
            detail="Background worker unavailable. Use /leads/scrape-sync instead.",
        )


@router.post("/scrape-sync")
async def scrape_sync(req: ScrapeRequest):
    """
    Synchronous scrape — runs Google Maps scraper in-process.
    Returns Server-Sent Events (SSE) so the frontend can show live progress.
    No Redis or Celery needed.
    """
    async def event_stream():
        job_id = str(uuid.uuid4())
        progress = {
            "job_id": job_id,
            "status": "running",
            "total_found": 0,
            "processed": 0,
            "inserted": 0,
            "skipped_duplicates": 0,
            "errors": 0,
        }

        def send(data):
            return f"data: {json.dumps(data)}\n\n"

        yield send(progress)

        # Step 1: Google Maps scrape (sync Playwright in thread — Windows safe)
        try:
            scraper = GoogleMapsScraper()
            raw_leads = await asyncio.to_thread(
                scraper.search_sync, req.keyword, req.location, req.max_results
            )
        except Exception as exc:
            progress["status"] = "failed"
            progress["error"] = str(exc)
            yield send(progress)
            return

        if raw_leads and isinstance(raw_leads[0], dict) and raw_leads[0].get("error") == "captcha":
            progress["status"] = "captcha_blocked"
            yield send(progress)
            return

        progress["total_found"] = len(raw_leads)
        yield send(progress)

        # Step 2: Process each lead
        for lead_data in raw_leads:
            try:
                company_name = lead_data.get("company_name")
                if not company_name or company_name.lower() in ("results", "google maps"):
                    progress["processed"] += 1
                    progress["errors"] += 1
                    yield send(progress)
                    continue

                # Duplicate check
                existing = (
                    supabase.table("leads")
                    .select("id")
                    .eq("company_name", company_name)
                    .eq("location", req.location)
                    .execute()
                )
                if existing.data:
                    progress["processed"] += 1
                    progress["skipped_duplicates"] += 1
                    yield send(progress)
                    continue

                # Website metadata enrichment
                website_meta = {}
                if lead_data.get("website"):
                    try:
                        website_meta = await scrape_website_meta(lead_data["website"])
                    except Exception:
                        pass

                raw_combined = {**lead_data, "website_meta": website_meta}
                lead_record = {
                    "company_name": company_name,
                    "website": lead_data.get("website"),
                    "location": req.location,
                    "city": None,
                    "country": None,
                    "industry": lead_data.get("category"),
                    "phone": lead_data.get("phone"),
                    "address": lead_data.get("address"),
                    "google_rating": lead_data.get("rating"),
                    "google_review_count": lead_data.get("review_count"),
                    "status": "new",
                    "raw_data": raw_combined,
                }

                insert_result = supabase.table("leads").insert(lead_record).execute()
                if insert_result.data:
                    progress["inserted"] += 1

                    # Try signal detection inline (non-blocking failure)
                    try:
                        from app.services.scorer import score_lead
                        new_id = insert_result.data[0]["id"]
                        await score_lead(new_id)
                    except Exception:
                        pass

            except Exception as exc:
                logger.error("Error processing lead %s: %s", lead_data.get("company_name"), exc, exc_info=True)
                progress["errors"] += 1

            progress["processed"] += 1
            yield send(progress)

        progress["status"] = "completed"
        yield send(progress)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/scrape-batch")
async def scrape_batch(req: BatchScrapeRequest):
    """
    Batch scrape — runs multiple keyword+location queries sequentially.
    Returns SSE progress for each query.
    """
    async def event_stream():
        batch_id = str(uuid.uuid4())
        totals = {
            "batch_id": batch_id,
            "status": "running",
            "current_query": 0,
            "total_queries": len(req.queries),
            "total_found": 0,
            "total_inserted": 0,
            "total_skipped": 0,
            "total_errors": 0,
            "current_keyword": "",
            "current_location": "",
        }

        def send(data):
            return f"data: {json.dumps(data)}\n\n"

        yield send(totals)

        for qi, query in enumerate(req.queries):
            totals["current_query"] = qi + 1
            totals["current_keyword"] = query.keyword
            totals["current_location"] = query.location
            yield send(totals)

            try:
                scraper = GoogleMapsScraper()
                raw_leads = await asyncio.to_thread(
                    scraper.search_sync, query.keyword, query.location, query.max_results
                )
            except Exception as exc:
                logger.error("Batch scrape error for %s/%s: %s", query.keyword, query.location, exc)
                totals["total_errors"] += 1
                yield send(totals)
                continue

            if raw_leads and isinstance(raw_leads[0], dict) and raw_leads[0].get("error") == "captcha":
                totals["status"] = "captcha_blocked"
                yield send(totals)
                return

            totals["total_found"] += len(raw_leads)
            yield send(totals)

            for lead_data in raw_leads:
                try:
                    company_name = lead_data.get("company_name")
                    if not company_name or company_name.lower() in ("results", "google maps"):
                        totals["total_errors"] += 1
                        yield send(totals)
                        continue

                    existing = (
                        supabase.table("leads")
                        .select("id")
                        .eq("company_name", company_name)
                        .eq("location", query.location)
                        .execute()
                    )
                    if existing.data:
                        totals["total_skipped"] += 1
                        yield send(totals)
                        continue

                    website_meta = {}
                    if lead_data.get("website"):
                        try:
                            website_meta = await scrape_website_meta(lead_data["website"])
                        except Exception:
                            pass

                    raw_combined = {**lead_data, "website_meta": website_meta}
                    lead_record = {
                        "company_name": company_name,
                        "website": lead_data.get("website"),
                        "location": query.location,
                        "city": None,
                        "country": None,
                        "industry": lead_data.get("category"),
                        "phone": lead_data.get("phone"),
                        "address": lead_data.get("address"),
                        "google_rating": lead_data.get("rating"),
                        "google_review_count": lead_data.get("review_count"),
                        "status": "new",
                        "raw_data": raw_combined,
                    }

                    insert_result = supabase.table("leads").insert(lead_record).execute()
                    if insert_result.data:
                        totals["total_inserted"] += 1
                        try:
                            from app.services.scorer import score_lead
                            new_id = insert_result.data[0]["id"]
                            await score_lead(new_id)
                        except Exception:
                            pass

                except Exception as exc:
                    logger.error("Batch: error processing lead %s: %s", lead_data.get("company_name"), exc, exc_info=True)
                    totals["total_errors"] += 1

                yield send(totals)

        totals["status"] = "completed"
        yield send(totals)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/scrape/status/{job_id}", response_model=ScrapeStatusResponse)
async def scrape_status(job_id: str):
    """
    Return real-time progress of a running scrape job.
    """
    from app.workers.scrape_tasks import get_job_status

    status = get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


# ═══════════════════════════════════════════════════════════════════════════
#  CRUD endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/")
async def list_leads(
    status: Optional[str] = Query(None, description="Filter by lead status"),
    min_score: Optional[int] = Query(None, description="Minimum lead score"),
    country: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    tag: Optional[str] = Query(None, description="Filter by tag (contains)"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Paginated lead listing.
    Default sort: lead_score DESC.
    """
    offset = (page - 1) * limit
    query = (
        supabase.table("leads")
        .select("*", count="exact")
        .neq("status", "dead")  # hide soft-deleted
        .order("lead_score", desc=True)
        .range(offset, offset + limit - 1)
    )

    if status:
        query = query.eq("status", status)
    if industry:
        query = query.eq("industry", industry)
    if country:
        query = query.eq("country", country)
    if min_score is not None:
        query = query.gte("lead_score", min_score)
    if tag:
        query = query.contains("tags", [tag])

    result = query.execute()

    return {
        "data": result.data,
        "total": result.count or len(result.data),
        "page": page,
        "limit": limit,
    }


@router.get("/{lead_id}")
async def get_lead(lead_id: str):
    """
    Get a single lead with related contacts and signals.
    """
    lead = (
        supabase.table("leads")
        .select("*")
        .eq("id", lead_id)
        .single()
        .execute()
    )
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Fetch related contacts
    contacts = (
        supabase.table("contacts")
        .select("*")
        .eq("lead_id", lead_id)
        .execute()
    )

    # Fetch related signals
    signals = (
        supabase.table("signals")
        .select("*")
        .eq("lead_id", lead_id)
        .order("detected_at", desc=True)
        .execute()
    )

    return {
        **lead.data,
        "contacts": contacts.data,
        "signals": signals.data,
    }


@router.post("/", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate):
    result = supabase.table("leads").insert(lead.model_dump()).execute()
    return result.data[0]


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: str, lead: LeadUpdate):
    data = lead.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = supabase.table("leads").update(data).eq("id", lead_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result.data[0]


@router.delete("/{lead_id}", status_code=200)
async def delete_lead(lead_id: str):
    """
    Soft-delete: sets status to 'dead' rather than removing the row.
    """
    result = (
        supabase.table("leads")
        .update({"status": "dead"})
        .eq("id", lead_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"detail": "Lead marked as dead"}
