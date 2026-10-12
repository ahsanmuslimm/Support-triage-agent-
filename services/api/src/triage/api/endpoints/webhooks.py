"""Webhook receivers for external integrations."""

import os

from fastapi import APIRouter, Header, HTTPException, Request

from ...ingestion.zendesk_webhook import ZendeskWebhookHandler

router = APIRouter()

# Initialize handlers
zendesk_handler = ZendeskWebhookHandler(
    webhook_secret=os.environ.get("ZENDESK_WEBHOOK_SECRET")
)


@router.post("/webhooks/zendesk")
async def receive_zendesk_webhook(
    request: Request,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    signature: str = Header(..., alias="X-Zendesk-Webhook-Signature"),
) -> dict:
    """Receive and process Zendesk webhook.

    Verifies HMAC-SHA256 signature, extracts message, and queues for ingestion.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID
        signature: HMAC signature from Zendesk

    Returns:
        {"status": "received"}

    Raises:
        HTTPException: If signature verification fails (401) or processing error (400)
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # Get raw body for signature verification
    raw_body = await request.body()
    raw_body_str = raw_body.decode("utf-8")

    # Verify signature
    if not zendesk_handler.verify_signature(raw_body_str, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload (validates JSON; the result is unused until ingestion is wired up)
    try:
        zendesk_handler.parse_payload(raw_body_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    # TODO: Extract message and queue for ingestion
    # message = zendesk_handler.extract_message(payload, tenant_id, conversation_id)
    # if message:
    #     await queue_message_for_ingestion(message)

    return {"status": "received"}
