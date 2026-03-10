from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import supabase

router = APIRouter(prefix="/settings", tags=["Settings"])


# ---------------------------------------------------------------------------
# Domain Health Check (Module 09)
# ---------------------------------------------------------------------------
@router.get("/domain-health")
async def domain_health_check(domain: Optional[str] = Query(None)):
    """
    Check DNS records (SPF, DKIM, DMARC) for your outreach domain.
    Pass ?domain=yourdomain.com — defaults to BREVO_SENDER_EMAIL's domain.
    """
    import dns.resolver
    from app.config import settings as app_settings

    if not domain:
        sender = app_settings.BREVO_SENDER_EMAIL
        if not sender or "@" not in sender:
            raise HTTPException(
                status_code=400,
                detail="No domain provided and BREVO_SENDER_EMAIL is not set. Pass ?domain=yourdomain.com",
            )
        domain = sender.split("@")[1]

    result = {
        "domain": domain,
        "spf": {"found": False, "valid": False, "record": None},
        "dkim": {"found": False, "valid": False, "record": None},
        "dmarc": {"found": False, "valid": False, "policy": None, "record": None},
        "overall_health": "critical",
    }

    # --- SPF ---
    try:
        answers = dns.resolver.resolve(domain, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith("v=spf1"):
                result["spf"]["found"] = True
                result["spf"]["record"] = txt
                result["spf"]["valid"] = "sendinblue.com" in txt or "brevo.com" in txt
                break
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        pass
    except Exception:
        pass

    # --- DKIM ---
    dkim_selectors = ["mail", "brevo", "sendinblue"]
    for selector in dkim_selectors:
        try:
            dkim_domain = f"{selector}._domainkey.{domain}"
            answers = dns.resolver.resolve(dkim_domain, "TXT")
            for rdata in answers:
                txt = rdata.to_text().strip('"')
                if "DKIM1" in txt or "p=" in txt:
                    result["dkim"]["found"] = True
                    result["dkim"]["valid"] = "p=" in txt and len(txt) > 50
                    result["dkim"]["record"] = txt[:120] + "..." if len(txt) > 120 else txt
                    break
            if result["dkim"]["found"]:
                break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            continue
        except Exception:
            continue

    # --- DMARC ---
    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith("v=DMARC1"):
                result["dmarc"]["found"] = True
                result["dmarc"]["record"] = txt
                if "p=reject" in txt:
                    result["dmarc"]["policy"] = "reject"
                    result["dmarc"]["valid"] = True
                elif "p=quarantine" in txt:
                    result["dmarc"]["policy"] = "quarantine"
                    result["dmarc"]["valid"] = True
                elif "p=none" in txt:
                    result["dmarc"]["policy"] = "none"
                    result["dmarc"]["valid"] = False  # monitoring only
                break
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        pass
    except Exception:
        pass

    # --- Overall score ---
    checks = [
        result["spf"]["found"] and result["spf"]["valid"],
        result["dkim"]["found"] and result["dkim"]["valid"],
        result["dmarc"]["found"],
    ]
    passed = sum(checks)
    if passed == 3:
        result["overall_health"] = "good"
    elif passed == 2:
        result["overall_health"] = "fair"
    elif passed == 1:
        result["overall_health"] = "poor"
    else:
        result["overall_health"] = "critical"

    return result


@router.get("/signal-definitions")
async def list_signal_definitions():
    """Get all signal definitions."""
    result = supabase.table("signal_definitions").select("*").execute()
    return result.data


@router.post("/signal-definitions")
async def create_signal_definition(definition: dict):
    """Create a new signal definition."""
    result = supabase.table("signal_definitions").insert(definition).execute()
    return result.data[0]


@router.patch("/signal-definitions/{definition_id}")
async def update_signal_definition(definition_id: str, definition: dict):
    """Update a signal definition."""
    result = (
        supabase.table("signal_definitions")
        .update(definition)
        .eq("id", definition_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Signal definition not found")
    return result.data[0]


@router.delete("/signal-definitions/{definition_id}", status_code=204)
async def delete_signal_definition(definition_id: str):
    """Delete a signal definition."""
    supabase.table("signal_definitions").delete().eq("id", definition_id).execute()
