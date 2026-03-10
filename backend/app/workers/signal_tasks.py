"""
Celery tasks for signal detection and lead scoring.

run_signal_detection  — full pipeline: detect signals → store → score → update lead
bulk_detect_signals   — queue detection for multiple leads
"""

import asyncio
import logging
from dataclasses import asdict

from app.workers.celery_app import celery_app
from app.services.signal_engine import SignalEngine
from app.services.scorer import LeadScorer
from app.database import supabase

logger = logging.getLogger(__name__)


@celery_app.task(name="signal_tasks.run_signal_detection")
def run_signal_detection(lead_id: str, campaign_id: str | None = None):
    """
    Full signal detection + scoring pipeline for a single lead.

    1. Fetch the lead record from Supabase
    2. Run SignalEngine.detect_all_signals()
    3. Persist every *detected* signal into the `signals` table
    4. Run LeadScorer.calculate_score()
    5. Update lead status → 'scored'
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # ── 1. Fetch lead ──────────────────────────────────────────────
        lead_resp = (
            supabase.table("leads")
            .select("*")
            .eq("id", lead_id)
            .single()
            .execute()
        )
        if not lead_resp.data:
            return {"lead_id": lead_id, "status": "skipped", "reason": "Lead not found"}

        lead = lead_resp.data
        raw_data = lead.get("raw_data") or {}

        if not raw_data:
            return {"lead_id": lead_id, "status": "skipped", "reason": "No raw data"}

        # ── 2. Detect signals ──────────────────────────────────────────
        engine = SignalEngine()
        signal_results = loop.run_until_complete(
            engine.detect_all_signals(lead, raw_data)
        )

        # ── 3. Store detected signals in DB ────────────────────────────
        # Remove old signals first (idempotent re-run)
        supabase.table("signals").delete().eq("lead_id", lead_id).execute()

        rows_to_insert = []
        for sig in signal_results:
            if sig.detected:
                rows_to_insert.append({
                    "lead_id": lead_id,
                    "signal_key": sig.signal_key,
                    "signal_value": sig.signal_value,
                    "signal_score": sig.score_contribution,
                })

        if rows_to_insert:
            supabase.table("signals").insert(rows_to_insert).execute()

        # ── 4. Score the lead ──────────────────────────────────────────
        scorer = LeadScorer()
        total_score, breakdown = scorer.calculate_score(
            lead_id, signal_results, campaign_id
        )

        # ── 5. Update status ───────────────────────────────────────────
        supabase.table("leads").update({"status": "scored"}).eq("id", lead_id).execute()

        detected_count = sum(1 for s in signal_results if s.detected)
        logger.info(
            "Lead %s: %d signals detected, score=%d",
            lead_id,
            detected_count,
            total_score,
        )

        return {
            "lead_id": lead_id,
            "signals_detected": detected_count,
            "signals_total": len(signal_results),
            "score": total_score,
            "status": "scored",
        }

    except Exception as exc:
        logger.error("Signal detection failed for %s: %s", lead_id, exc)
        return {"lead_id": lead_id, "status": "error", "error": str(exc)}
    finally:
        loop.close()


# ── Backward-compat alias (used by scrape_tasks) ──────────────────────────
detect_lead_signals = run_signal_detection


@celery_app.task(name="signal_tasks.bulk_detect_signals")
def bulk_detect_signals(lead_ids: list, campaign_id: str | None = None):
    """Queue signal detection for multiple leads."""
    results = []
    for lead_id in lead_ids:
        run_signal_detection.delay(lead_id, campaign_id)
        results.append({"lead_id": lead_id, "queued": True})
    return results
