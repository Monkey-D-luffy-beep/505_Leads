"""
Brevo Webhook Router — handles email event callbacks.

Endpoint:
  POST /api/v1/webhooks/brevo  → process delivery/open/bounce/spam events

Brevo sends POST requests for: delivered, opened, clicked,
soft_bounce, hard_bounce, unsubscribe, spam, invalid_email.

Always returns HTTP 200 immediately — Brevo retries on non-200.
"""

import logging
from fastapi import APIRouter, Request, Response

from app.services.reply_tracker import BrevoWebhookHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/brevo")
async def brevo_webhook(request: Request):
    """
    Receive and process Brevo email event webhooks.

    Expected payload fields:
      - event: str  (delivered | opened | clicked | hard_bounce | soft_bounce | unsubscribe | spam | invalid_email)
      - email: str  (recipient email)
      - message-id: str  (our tracking_id)
      - date / ts_event: str (event timestamp)

    Always returns 200 to prevent Brevo retries.
    """
    try:
        payload = await request.json()
    except Exception:
        # Brevo sometimes sends form-encoded
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            logger.warning("Brevo webhook: could not parse payload")
            return Response(status_code=200)

    event_type = payload.get("event", "").lower()

    if not event_type:
        logger.warning("Brevo webhook: no event type in payload")
        return Response(status_code=200)

    logger.info(
        "Brevo webhook received: event=%s email=%s",
        event_type,
        payload.get("email", "unknown"),
    )

    try:
        result = BrevoWebhookHandler.handle_event(event_type, payload)
        logger.info("Brevo webhook processed: %s", result)
    except Exception as exc:
        # Log but still return 200 — don't make Brevo retry
        logger.exception("Brevo webhook processing error: %s", exc)

    return Response(status_code=200)
