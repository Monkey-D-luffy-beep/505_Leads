"""
Celery tasks for web scraping operations.

run_scrape_job  — main task: Google Maps search → website meta → insert leads
scrape_lead_website — scrape a single lead's website for metadata
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.services.scraper import GoogleMapsScraper, scrape_website_meta
from app.database import supabase
from app.config import settings

logger = logging.getLogger(__name__)

# ── Redis helper for job progress tracking ─────────────────────────────────

try:
    import redis as _redis

    _redis_client = _redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception:
    _redis_client = None


def _update_job(job_id: str, data: dict) -> None:
    """Persist job progress to Redis (key: scrape_job:{job_id})."""
    if _redis_client:
        key = f"scrape_job:{job_id}"
        _redis_client.set(key, json.dumps(data), ex=86400)  # 24h TTL


def get_job_status(job_id: str) -> dict | None:
    """Read job progress from Redis."""
    if _redis_client:
        raw = _redis_client.get(f"scrape_job:{job_id}")
        if raw:
            return json.loads(raw)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Main scrape job
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(bind=True, name="scrape_tasks.run_scrape_job", max_retries=2)
def run_scrape_job(
    self,
    keyword: str,
    location: str,
    max_results: int = 50,
    job_id: str | None = None,
):
    """
    Full scrape pipeline:
    1. Google Maps search → raw leads
    2. For each lead with a website → scrape_website_meta
    3. De-duplicate against Supabase
    4. Insert new leads
    5. Trigger signal detection per lead
    6. Track progress in Redis
    """
    if not job_id:
        job_id = str(uuid.uuid4())

    progress = {
        "job_id": job_id,
        "keyword": keyword,
        "location": location,
        "status": "running",
        "total_found": 0,
        "processed": 0,
        "inserted": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _update_job(job_id, progress)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # ── Step 1: Google Maps scrape ─────────────────────────────────
        scraper = GoogleMapsScraper()
        raw_leads = loop.run_until_complete(
            scraper.search(keyword, location, max_results)
        )

        # Handle CAPTCHA error
        if raw_leads and isinstance(raw_leads[0], dict) and raw_leads[0].get("error") == "captcha":
            progress["status"] = "captcha_blocked"
            progress["finished_at"] = datetime.now(timezone.utc).isoformat()
            _update_job(job_id, progress)
            return progress

        progress["total_found"] = len(raw_leads)
        _update_job(job_id, progress)

        # ── Step 2 & 3: Enrich, de-dup, insert ────────────────────────
        for lead_data in raw_leads:
            try:
                company_name = lead_data.get("company_name")
                if not company_name:
                    progress["processed"] += 1
                    progress["errors"] += 1
                    _update_job(job_id, progress)
                    continue

                # ── Duplicate check ────────────────────────────────────
                existing = (
                    supabase.table("leads")
                    .select("id")
                    .eq("company_name", company_name)
                    .eq("location", location)
                    .execute()
                )
                if existing.data:
                    progress["processed"] += 1
                    progress["skipped_duplicates"] += 1
                    _update_job(job_id, progress)
                    continue

                # ── Scrape website metadata (if website exists) ────────
                website_meta = {}
                if lead_data.get("website"):
                    try:
                        website_meta = loop.run_until_complete(
                            scrape_website_meta(lead_data["website"])
                        )
                    except Exception as meta_exc:
                        logger.warning(
                            "Website meta failed for %s: %s",
                            lead_data["website"],
                            meta_exc,
                        )

                # ── Build lead record ──────────────────────────────────
                raw_combined = {**lead_data, "website_meta": website_meta}

                lead_record = {
                    "company_name": company_name,
                    "website": lead_data.get("website"),
                    "location": location,
                    "city": None,  # can be parsed later
                    "country": None,
                    "industry": lead_data.get("category"),
                    "phone": lead_data.get("phone"),
                    "address": lead_data.get("address"),
                    "google_rating": lead_data.get("rating"),
                    "google_review_count": lead_data.get("review_count"),
                    "status": "new",
                    "raw_data": raw_combined,
                }

                # ── Insert into Supabase ───────────────────────────────
                insert_result = (
                    supabase.table("leads")
                    .insert(lead_record)
                    .execute()
                )

                if insert_result.data:
                    new_lead_id = insert_result.data[0]["id"]
                    progress["inserted"] += 1

                    # ── Trigger signal detection ───────────────────────
                    try:
                        from app.workers.signal_tasks import detect_lead_signals
                        detect_lead_signals.delay(new_lead_id)
                    except Exception:
                        logger.warning(
                            "Could not queue signal detection for %s",
                            new_lead_id,
                        )

            except Exception as exc:
                logger.error("Error processing lead %s: %s", lead_data.get("company_name"), exc)
                progress["errors"] += 1

            progress["processed"] += 1
            _update_job(job_id, progress)

        # ── Done ───────────────────────────────────────────────────────
        progress["status"] = "completed"
        progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        _update_job(job_id, progress)

    except Exception as exc:
        logger.error("Scrape job %s failed: %s", job_id, exc)
        progress["status"] = "failed"
        progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        _update_job(job_id, progress)
        raise self.retry(exc=exc, countdown=60)

    finally:
        loop.close()

    return progress


# ═══════════════════════════════════════════════════════════════════════════
#  Single-lead website scrape (for re-scraping existing leads)
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(name="scrape_tasks.scrape_lead_website")
def scrape_lead_website(lead_id: str, url: str):
    """Scrape a lead's website for metadata and store in raw_data."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(scrape_website_meta(url))

        # Merge website meta into existing raw_data
        lead = (
            supabase.table("leads")
            .select("raw_data")
            .eq("id", lead_id)
            .single()
            .execute()
        )
        existing_raw = lead.data.get("raw_data", {}) if lead.data else {}
        existing_raw["website_meta"] = result

        supabase.table("leads").update({
            "raw_data": existing_raw,
        }).eq("id", lead_id).execute()

        return {"lead_id": lead_id, "status": "scraped", "data": result}
    finally:
        loop.close()


@celery_app.task(name="scrape_tasks.bulk_scrape")
def bulk_scrape(lead_ids: list):
    """Queue website scraping tasks for multiple existing leads."""
    results = []
    for lead_id in lead_ids:
        lead = (
            supabase.table("leads")
            .select("id, website")
            .eq("id", lead_id)
            .single()
            .execute()
        )
        if lead.data and lead.data.get("website"):
            scrape_lead_website.delay(lead_id, lead.data["website"])
            results.append({"lead_id": lead_id, "queued": True})
        else:
            results.append({"lead_id": lead_id, "queued": False, "reason": "No website"})
    return results
