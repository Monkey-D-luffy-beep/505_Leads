"""
Seed script — populate signal_definitions with Tier 1 + Tier 2 defaults.

Usage:
    cd backend
    python -m scripts.seed_signals

Idempotent: skips any signal_key that already exists.
"""

import sys
import os

# Allow running from `backend/` directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import supabase  # noqa: E402


# ── Tier 1 — Universal (always collected) ──────────────────────────────────

TIER_1_SIGNALS = [
    {
        "signal_key": "has_website",
        "label": "Has a website",
        "description": "Lead has a website URL present",
        "tier": 1,
        "default_weight": 10,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_ssl",
        "label": "Website has SSL",
        "description": "Website uses HTTPS",
        "tier": 1,
        "default_weight": 5,
        "detection_type": "auto",
    },
    {
        "signal_key": "is_mobile_friendly",
        "label": "Mobile responsive",
        "description": "Website has viewport meta tag or responsive CSS",
        "tier": 1,
        "default_weight": 8,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_social_presence",
        "label": "Has social media links",
        "description": "Website links to Facebook, LinkedIn, Instagram, Twitter, or X",
        "tier": 1,
        "default_weight": 5,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_google_reviews",
        "label": "Has Google reviews",
        "description": "Lead has at least 1 Google review",
        "tier": 1,
        "default_weight": 8,
        "detection_type": "auto",
    },
    {
        "signal_key": "high_rating",
        "label": "Rating above 4.0",
        "description": "Google Maps rating is 4.0 or higher",
        "tier": 1,
        "default_weight": 10,
        "detection_type": "auto",
    },
    {
        "signal_key": "low_review_count",
        "label": "Fewer than 20 reviews",
        "description": "Has reviews but fewer than 20 — room for growth",
        "tier": 1,
        "default_weight": 15,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_contact_form",
        "label": "Has a contact form",
        "description": "Website contains a form with an email input",
        "tier": 1,
        "default_weight": 10,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_phone_number",
        "label": "Phone number listed",
        "description": "Lead has a phone number on Google Maps or website",
        "tier": 1,
        "default_weight": 5,
        "detection_type": "auto",
    },
    {
        "signal_key": "small_business",
        "label": "Estimated 1-20 employees",
        "description": "Small business by employee estimate or category",
        "tier": 1,
        "default_weight": 20,
        "detection_type": "auto",
    },
]


# ── Tier 2 — Tech Signals (always collected, weight varies per campaign) ───

TIER_2_SIGNALS = [
    {
        "signal_key": "uses_wordpress",
        "label": "Website on WordPress",
        "description": "Detected /wp-content/ or /wp-includes/ in HTML",
        "tier": 2,
        "default_weight": 10,
        "detection_type": "auto",
    },
    {
        "signal_key": "uses_wix_squarespace",
        "label": "Website on Wix/Squarespace",
        "description": "Detected wix.com or squarespace.com scripts",
        "tier": 2,
        "default_weight": 15,
        "detection_type": "auto",
    },
    {
        "signal_key": "uses_shopify",
        "label": "Has Shopify store",
        "description": "Detected cdn.shopify.com in page source",
        "tier": 2,
        "default_weight": 10,
        "detection_type": "auto",
    },
    {
        "signal_key": "no_analytics",
        "label": "No analytics tool detected",
        "description": "No Google Analytics, Matomo, Plausible, or Fathom found",
        "tier": 2,
        "default_weight": 20,
        "detection_type": "auto",
    },
    {
        "signal_key": "no_chat_tool",
        "label": "No live chat tool",
        "description": "No Intercom, Drift, Tawk.to, Zendesk, Crisp, Tidio, or Olark found",
        "tier": 2,
        "default_weight": 15,
        "detection_type": "auto",
    },
    {
        "signal_key": "no_crm_pixel",
        "label": "No CRM pixel detected",
        "description": "No HubSpot, Intercom, or Drift tracking pixel found",
        "tier": 2,
        "default_weight": 20,
        "detection_type": "auto",
    },
    {
        "signal_key": "runs_paid_ads",
        "label": "Running Google/Meta ads",
        "description": "Detected Google Ads or Meta Pixel on website",
        "tier": 2,
        "default_weight": 25,
        "detection_type": "auto",
    },
    {
        "signal_key": "has_booking_widget",
        "label": "Has online booking",
        "description": "Calendly, Acuity, or similar booking system detected",
        "tier": 2,
        "default_weight": -10,
        "detection_type": "auto",
    },
    {
        "signal_key": "no_booking_widget",
        "label": "No online booking",
        "description": "No online booking system detected — opportunity to sell one",
        "tier": 2,
        "default_weight": 20,
        "detection_type": "auto",
    },
    {
        "signal_key": "old_cms_version",
        "label": "Using outdated CMS",
        "description": "WordPress version below 6.x or other outdated CMS detected",
        "tier": 2,
        "default_weight": 15,
        "detection_type": "auto",
    },
    {
        "signal_key": "no_email_marketing",
        "label": "No email marketing tool",
        "description": "No Mailchimp, Klaviyo, or similar tool detected",
        "tier": 2,
        "default_weight": 15,
        "detection_type": "auto",
    },
]


def seed():
    """Insert Tier 1 + Tier 2 signal definitions (skip existing keys)."""
    all_signals = TIER_1_SIGNALS + TIER_2_SIGNALS

    # Fetch existing keys
    existing = supabase.table("signal_definitions").select("signal_key").execute()
    existing_keys = {row["signal_key"] for row in (existing.data or [])}

    inserted = 0
    skipped = 0

    for sig in all_signals:
        if sig["signal_key"] in existing_keys:
            skipped += 1
            continue

        supabase.table("signal_definitions").insert(sig).execute()
        inserted += 1
        print(f"  + {sig['signal_key']} (Tier {sig['tier']})")

    print(f"\nDone. Inserted: {inserted}, Skipped (already exist): {skipped}")


if __name__ == "__main__":
    print("Seeding signal definitions...\n")
    seed()
