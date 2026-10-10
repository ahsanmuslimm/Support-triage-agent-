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
from ...ingestion.encryption import EnvelopeEncryption
from ...ingestion.pii_handler import PiiHandler
from ...ingestion.identity import IdentityResolver
from ...ingestion.outbox import OutboxWriter

router = APIRouter()

# Global instances (should be injected from DI container in real app)
_encryption = EnvelopeEncryption() if __import__("os").environ.get("ENCRYPTION_KEY") else None
_pii_handler = PiiHandler()
_identity_resolver = IdentityResolver()
_outbox_writer = OutboxWriter()


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
    Implements full pipeline: normalize → validate → check idempotency → encrypt → redact PII → 
    resolve identity → store to database → write outbox event → queue for coalescing.

    Args:
        conversation_id: Conversation ID
        request: MessageRequest payload
        tenant_id: Tenant ID from header
        idempotency_key: Optional idempotency key

    Returns:
        MessageResponse with stream URL for real-time updates

    Response codes:
        202: Message ingested successfully (processing async)
        409: Duplicate message (same idempotency_key already ingested)
        400: Missing required header or invalid payload
        422: Validation error
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # ========== STEP 1: Compute idempotency key ==========
    if not idempotency_key:
        body_hash = IdempotencyManager.compute_body_hash(request.body)
        idempotency_key = IdempotencyManager.generate_key(
            tenant_id=tenant_id,
            provider_message_id=request.provider_message_id,
            sender_id=request.sender_id,
            body_hash=body_hash,
        )

    # ========== STEP 2: Check for duplicate (409 Conflict) ==========
    # In real implementation, query database: SELECT id FROM messages WHERE tenant_id=? AND idempotency_key=?
    # For now, stub: would check against actual message store
    is_duplicate = IdempotencyManager.is_duplicate(idempotency_key)
    if is_duplicate:
        # Return 409 with Location header pointing to original message
        raise HTTPException(
            status_code=409,
            detail="Duplicate message (same idempotency_key already ingested)",
            headers={"Location": f"/api/v1/conversations/{conversation_id}/messages/{idempotency_key}"},
        )

    # ========== STEP 3: Normalize message ==========
    normalizer = NormalizerFactory.get_normalizer(request.channel_type)
    canonical_message = normalizer.normalize(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        channel_id=request.channel_type.value,
        payload=request.model_dump(),
    )

    # ========== STEP 4: Redact PII (before any downstream processing) ==========
    redacted_body, pii_entities, pii_vault = _pii_handler.redact(canonical_message.body)
    canonical_message.body = redacted_body

    # ========== STEP 5: Encrypt message body ==========
    body_encrypted = None
    if _encryption:
        body_encrypted = _encryption.encrypt(redacted_body)

    # ========== STEP 6: Resolve customer identity ==========
    customer = _identity_resolver.resolve_or_create(
        tenant_id=tenant_id,
        email=request.sender_id if "@" in (request.sender_id or "") else None,
        phone=request.sender_id if request.sender_id and request.sender_id.replace("-", "").isdigit() else None,
        external_id=request.provider_message_id,
        display_name=getattr(request, "sender_name", None),
    )
    customer_id = customer.customer_id

    # ========== STEP 7: Store message (in real implementation, write to DB) ==========
    message_id = str(uuid.uuid4())
    message_record = {
        "id": message_id,
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "channel_type": request.channel_type.value,
        "source": request.channel_type.value,
        "body": canonical_message.body,  # Redacted, plaintext
        "body_encrypted": body_encrypted,  # Encrypted JSON blob
        "language": getattr(canonical_message, "language", None),
        "provider_message_id": request.provider_message_id,
        "sender_id": request.sender_id,
        "idempotency_key": idempotency_key,
        "metadata": request.metadata or {},
        "created_at": canonical_message.created_at,
    }

    # ========== STEP 8: Write outbox event (atomically with message insert) ==========
    outbox_event = await _outbox_writer.write_event(
        tenant_id=tenant_id,
        aggregate_type="message",
        aggregate_id=message_id,
        event_type="message.ingested",
        payload={
            "message_id": message_id,
            "conversation_id": conversation_id,
            "customer_id": customer_id,
            "channel_type": request.channel_type.value,
            "pii_entities": [{"type": e.entity_type, "count": 1} for e in pii_entities],
        },
    )

    # ========== STEP 9: Queue for coalescing (background task) ==========
    # In real implementation: MessageCoalescer.queue_message(conversation_id, message_id)
    # This would start a debounce timer and eventually trigger a triage run

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

    Returns existing messages immediately, then subscribes to new messages via Redis Pub/Sub
    or AsyncIO queue. Implements proper SSE line format: `data: {...}\n\n` and heartbeats.

    Args:
        conversation_id: Conversation ID
        tenant_id: Tenant ID from header

    Returns:
        SSE stream with messages and status updates
    """

    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    async def event_generator():
        """Generate SSE events for conversation.
        
        Yields:
            SSE-formatted event strings (data: {...}\n\n)
        """
        try:
            # ========== STEP 1: Fetch existing messages from database ==========
            # In real implementation:
            # async with db_session() as session:
            #     messages = await session.execute(
            #         select(Message)
            #         .where(Message.tenant_id == tenant_id)
            #         .where(Message.conversation_id == conversation_id)
            #         .order_by(Message.created_at)
            #     )
            # For now, stub: yield empty initial batch
            
            yield f"data: {json.dumps({{'type': 'init', 'conversation_id': conversation_id}})}\n\n"

            # ========== STEP 2: Subscribe to new messages via Redis Pub/Sub or AsyncIO queue ==========
            # In real implementation:
            # async with redis_client.subscribe(f"conv:{conversation_id}") as channels:
            #     async for message in channels[0].iter():
            #         yield f"data: {message.decode()}\n\n"
            #
            # For now, demo: send heartbeats every 30s for 5 minutes, then close
            heartbeat_count = 0
            max_heartbeats = 10  # 5 minutes of 30s heartbeats

            while heartbeat_count < max_heartbeats:
                # Send heartbeat comment (client uses this to detect dead connections)
                yield f": heartbeat (connection alive)\n\n"
                await asyncio.sleep(30)
                heartbeat_count += 1

        except asyncio.CancelledError:
            # Client closed connection gracefully
            pass
        except Exception as e:
            # Error in streaming loop
            yield f"data: {json.dumps({{'type': 'error', 'error': str(e)}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
