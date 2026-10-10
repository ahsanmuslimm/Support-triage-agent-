"""Message ingestion and streaming endpoints."""

from fastapi import APIRouter, HTTPException, Header, Response
from fastapi.responses import StreamingResponse
import asyncio
import json
from typing import Optional
import uuid

from ...models.message import MessageRequest, MessageResponse, MessageStatus, ChannelType
from ...ingestion.normalizers import NormalizerFactory
from ...ingestion.idempotency import IdempotencyManager

router = APIRouter()


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=202,
    response_model=MessageResponse,
)
async def ingest_message(
    conversation_id: str,
    request: MessageRequest,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> MessageResponse:
    """Ingest a message into a conversation.

    Returns 202 Accepted immediately. Message is processed asynchronously.

    Args:
        conversation_id: Conversation ID
        request: MessageRequest payload
        tenant_id: Tenant ID from header
        idempotency_key: Optional idempotency key

    Returns:
        MessageResponse with stream URL for real-time updates
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # Generate idempotency key if not provided
    if not idempotency_key:
        body_hash = IdempotencyManager.compute_body_hash(request.body)
        idempotency_key = IdempotencyManager.generate_key(
            tenant_id=tenant_id,
            provider_message_id=request.provider_message_id,
            sender_id=request.sender_id,
            body_hash=body_hash,
        )

    # TODO: Check for duplicate (would return 409 Conflict if duplicate)

    # Normalize message
    normalizer = NormalizerFactory.get_normalizer(request.channel_type)
    canonical_message = normalizer.normalize(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        channel_id=request.channel_type.value,
        payload=request.model_dump(),
    )

    # TODO: Encrypt body
    # TODO: Redact PII
    # TODO: Resolve identity
    # TODO: Store message in database
    # TODO: Write to outbox
    # TODO: Queue for coalescing

    message_id = str(uuid.uuid4())
    stream_url = f"/api/v1/streams/conversations/{conversation_id}"

    return MessageResponse(
        id=message_id,
        conversation_id=conversation_id,
        status=MessageStatus.INGESTED,
        idempotency_key=idempotency_key,
        stream_url=stream_url,
        created_at=canonical_message.created_at,
    )


@router.get("/streams/conversations/{conversation_id}")
async def stream_conversation(
    conversation_id: str,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> StreamingResponse:
    """Stream real-time updates for a conversation via Server-Sent Events.

    Args:
        conversation_id: Conversation ID
        tenant_id: Tenant ID from header

    Returns:
        SSE stream with messages and status updates
    """

    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    async def event_generator():
        """Generate SSE events for conversation."""
        # TODO: Fetch existing messages from database
        # initial_messages = await get_conversation_messages(conversation_id)
        # for msg in initial_messages:
        #     yield f"data: {json.dumps(msg)}\n\n"

        # TODO: Subscribe to new messages via Redis Pub/Sub or AsyncIO queue
        # Keep connection open and send updates
        counter = 0
        while counter < 10:  # Demo: send 10 heartbeats then close
            yield f": heartbeat\n\n"
            await asyncio.sleep(30)
            counter += 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
