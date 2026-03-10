"""
Lead Scorer — Calculates lead scores based on detected signals and
configurable weights (global defaults + campaign-specific overrides).
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

from app.database import supabase

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  LeadScorer
# ═══════════════════════════════════════════════════════════════════════════


class LeadScorer:
    """Score a lead by combining its signal results with weights."""

    def calculate_score(
        self,
        lead_id: str,
        signal_results: List[Any],
        campaign_id: Optional[str] = None,
    ) -> Tuple[int, Dict[str, Dict]]:
        """
        Calculate a lead's score.

        Parameters
        ----------
        lead_id : str
            UUID of the lead.
        signal_results : list
            List of SignalResult dataclass instances (from SignalEngine).
        campaign_id : str, optional
            If provided, campaign-specific weights override global defaults.

        Returns
        -------
        (total_score, score_breakdown) — score is 0-100 capped.
        """
        # ── 1. Load default weights from signal_definitions ────────────
        defs = supabase.table("signal_definitions").select("signal_key, default_weight").execute()
        default_weights: Dict[str, int] = {
            d["signal_key"]: d["default_weight"] for d in (defs.data or [])
        }

        # ── 2. Load campaign-specific weight overrides ─────────────────
        campaign_weights: Dict[str, int] = {}
        if campaign_id:
            camp = (
                supabase.table("campaigns")
                .select("signal_weights")
                .eq("id", campaign_id)
                .single()
                .execute()
            )
            if camp.data and camp.data.get("signal_weights"):
                campaign_weights = camp.data["signal_weights"]

        # ── 3. Score each signal ───────────────────────────────────────
        total_score: float = 0
        breakdown: Dict[str, Dict] = {}

        for sig in signal_results:
            # Support both dataclass (has .signal_key) and dict
            if hasattr(sig, "signal_key"):
                key = sig.signal_key
                detected = sig.detected
                value = sig.signal_value
            else:
                key = sig.get("signal_key", "")
                detected = sig.get("detected", False)
                value = sig.get("signal_value", "")

            # Campaign weight overrides global default
            weight = campaign_weights.get(key, default_weights.get(key, 10))

            contribution = weight if detected else 0
            total_score += contribution

            breakdown[key] = {
                "detected": detected,
                "weight": weight,
                "contribution": contribution,
                "value": value,
            }

        # ── 4. Cap score at 0-100 ──────────────────────────────────────
        total_score = max(0, min(int(total_score), 100))

        # ── 5. Persist to leads table ──────────────────────────────────
        new_status = "scored" if total_score > 0 else "new"
        supabase.table("leads").update({
            "lead_score": total_score,
            "score_breakdown": breakdown,
            "status": new_status,
        }).eq("id", lead_id).execute()

        logger.info("Lead %s scored %d (%s)", lead_id, total_score, new_status)
        return total_score, breakdown


# ═══════════════════════════════════════════════════════════════════════════
#  Convenience function wrappers (backward compat with older code)
# ═══════════════════════════════════════════════════════════════════════════


async def score_lead(
    lead_id: str,
    campaign_id: Optional[str] = None,
) -> Dict:
    """
    Re-score a lead using signals already stored in the `signals` table.
    Used for re-scoring after weight changes.
    """
    # Get signals already in DB
    db_signals = (
        supabase.table("signals").select("*").eq("lead_id", lead_id).execute()
    )

    # Convert DB rows into signal-result-like dicts
    signal_results = []
    for s in (db_signals.data or []):
        signal_results.append({
            "signal_key": s["signal_key"],
            "signal_value": s.get("signal_value", ""),
            "detected": True,  # if it's in the signals table, it was detected
        })

    scorer = LeadScorer()
    total, breakdown = scorer.calculate_score(lead_id, signal_results, campaign_id)
    return {"lead_id": lead_id, "score": total, "breakdown": breakdown}


async def bulk_score_leads(
    lead_ids: List[str],
    campaign_id: Optional[str] = None,
) -> List[Dict]:
    """Score multiple leads sequentially."""
    results = []
    for lid in lead_ids:
        r = await score_lead(lid, campaign_id)
        results.append(r)
    return results
