"""Message ingestion and streaming endpoints (DB-backed)."""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...db import SessionDep, TenantDep, stable_uuid
from ...ingestion.encryption import EnvelopeEncryption
from ...ingestion.idempotency import IdempotencyManager
from ...ingestion.normalizers import NormalizerFactory
from ...ingestion.pii_handler import PiiHandler
from ...models.message import MessageRequest, MessageResponse, MessageStatus
from ...models.orm import (
    Conversation,
    Customer,
    OutboxEventORM,
    PiiToken,
    Tenant,
)
from ...models.orm import Message as MessageORM

router = APIRouter()

_encryption = EnvelopeEncryption() if os.environ.get("ENCRYPTION_KEY") else None
_pii_handler = PiiHandler()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _resolve_customer(
    session,
    tenant_id: uuid.UUID,
    sender_id: str,
    sender_email: str | None,
) -> Customer:
    """Find or create the customer identity (deduped by email hash)."""
    email = sender_email or (sender_id if "@" in (sender_id or "") else None)
    email_hash = _sha256(email or sender_id)
    phone_hash = _sha256(sender_id) if sender_id and sender_id.replace("-", "").isdigit() else None

    result = await session.execute(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.email_hash == email_hash)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            email_hash=email_hash,
            phone_hash=phone_hash,
            external_id=sender_id if email is None else None,
        )
        session.add(customer)
        await session.flush()
    return customer


async def _resolve_conversation(
    session,
    tenant_id: uuid.UUID,
    conversation_id: str,
    customer_id: uuid.UUID,
    channel_id: str,
) -> Conversation:
    """Find or create the conversation; bumps message_count on existing rows."""
    conv_uuid = stable_uuid(conversation_id)
    conversation = await session.get(Conversation, (tenant_id, conv_uuid))
    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            id=conv_uuid,
            customer_id=customer_id,
            channel_id=channel_id,
            message_count=1,
            last_message_at=datetime.now(UTC),
        )
        session.add(conversation)
        await session.flush()
    else:
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(UTC)
    return conversation


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=202,
    response_model=MessageResponse,
)
async def ingest_message(
    conversation_id: str,
    request: MessageRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MessageResponse:
    """Ingest a message into a conversation.

    Returns 202 Accepted immediately. Message is processed asynchronously.
    Pipeline: normalize -> check idempotency -> resolve customer/conversation ->
    redact PII -> encrypt -> persist message + outbox event in one transaction.

    Response codes:
        202: Message ingested successfully (processing async)
        409: Duplicate message (same idempotency_key already ingested)
        400: Missing/invalid headers
        422: Validation error
        503: Database not initialized or unavailable
    """
    # ========== STEP 1: Ensure tenant exists (auto-provision on first use) ==========
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        session.add(Tenant(id=tenant_id, slug=f"tenant-{str(tenant_id)[:8]}", name=str(tenant_id)))
        await session.flush()

    # ========== STEP 2: Compute idempotency key ==========
    if not idempotency_key:
        body_hash = IdempotencyManager.compute_body_hash(request.body)
        idempotency_key = IdempotencyManager.generate_key(
            tenant_id=str(tenant_id),
            provider_message_id=request.provider_message_id,
            sender_id=request.sender_id,
            body_hash=body_hash,
        )

    # ========== STEP 3: Check for duplicate (409 Conflict) ==========
    existing = (
        await session.execute(
            select(MessageORM.id).where(
                MessageORM.tenant_id == tenant_id,
                MessageORM.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Duplicate message (same idempotency_key already ingested)",
            headers={"Location": f"/api/v1/conversations/{conversation_id}/messages/{existing}"},
        )

    # ========== STEP 4: Resolve customer identity ==========
    customer = await _resolve_customer(session, tenant_id, request.sender_id, request.sender_email)

    # ========== STEP 5: Resolve conversation ==========
    conversation = await _resolve_conversation(
        session, tenant_id, conversation_id, customer.id, request.channel_type.value
    )

    # ========== STEP 6: Normalize message ==========
    normalizer = NormalizerFactory.get_normalizer(request.channel_type)
    canonical_message = normalizer.normalize(
        tenant_id=str(tenant_id),
        conversation_id=str(conversation.id),
        channel_id=request.channel_type.value,
        payload=request.model_dump(),
    )

    # ========== STEP 7: Redact PII (before any downstream processing) ==========
    redacted_body, pii_entities, pii_vault = _pii_handler.redact(canonical_message.body)
    canonical_message.body = redacted_body

    # ========== STEP 8: Encrypt message body ==========
    body_encrypted: dict[str, Any] | None = None
    if _encryption:
        body_encrypted = _encryption.encrypt(redacted_body)

    # ========== STEP 9: Persist message + outbox event in one transaction ==========
    message_id = uuid.uuid4()
    session.add(
        MessageORM(
            tenant_id=tenant_id,
            id=message_id,
            conversation_id=conversation.id,
            customer_id=customer.id,
            channel_type=request.channel_type.value,
            source=request.channel_type.value,
            body=redacted_body,
            body_encrypted=body_encrypted,
            language=getattr(canonical_message, "language", None),
            provider_message_id=request.provider_message_id,
            sender_id=request.sender_id,
            idempotency_key=idempotency_key,
            metadata_json=request.metadata or {},
        )
    )
    for entity in pii_entities:
        value = pii_vault[entity.token]
        encrypted_value = _encryption.encrypt(value)["ciphertext"] if _encryption else None
        session.add(
            PiiToken(
                tenant_id=tenant_id,
                pii_type=entity.entity_type,
                pii_hash=_sha256(value),
                token=entity.token,
                message_id=message_id,
                encrypted_value=encrypted_value,
            )
        )
    session.add(
        OutboxEventORM(
            tenant_id=tenant_id,
            aggregate_type="message",
            aggregate_id=message_id,
            event_type="message.ingested",
            payload={
                "message_id": str(message_id),
                "conversation_id": str(conversation.id),
                "customer_id": str(customer.id),
                "channel_type": request.channel_type.value,
                "pii_entities": [{"type": e.entity_type, "count": 1} for e in pii_entities],
            },
        )
    )

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        # Raced with a concurrent ingest of the same idempotency key
        raise HTTPException(
            status_code=409,
            detail="Duplicate message (same idempotency_key already ingested)",
        ) from e

    return MessageResponse(
        id=str(message_id),
        conversation_id=str(conversation.id),
        status=MessageStatus.INGESTED,
        idempotency_key=idempotency_key,
        stream_url=f"/api/v1/streams/conversations/{conversation.id}",
        created_at=canonical_message.created_at,
    )


@router.get("/streams/conversations/{conversation_id}")
async def stream_conversation(
    conversation_id: str,
    session: SessionDep,
    tenant_id: TenantDep,
) -> StreamingResponse:
    """Stream real-time updates for a conversation via Server-Sent Events.

    Replays existing messages from the database, then keeps the connection
    alive with heartbeats (Redis Pub/Sub fan-in arrives with the workers).
    """
    conv_uuid = stable_uuid(conversation_id)
    messages: list[MessageORM] = []

    result = await session.execute(
        select(MessageORM)
        .where(MessageORM.tenant_id == tenant_id, MessageORM.conversation_id == conv_uuid)
        .order_by(MessageORM.created_at)
    )
    messages = list(result.scalars().all())
    # Release the read transaction before the long-lived stream loop
    await session.rollback()

    async def event_generator():
        """Yield SSE events: init + replayed messages, then heartbeats."""
        try:
            yield f"data: {json.dumps({'type': 'init', 'conversation_id': str(conv_uuid)})}\n\n"
            for m in messages:
                yield f"data: {json.dumps({'type': 'message', 'id': str(m.id), 'body': m.body, 'sender_id': m.sender_id, 'channel_type': m.channel_type, 'created_at': m.created_at.isoformat() if m.created_at else None})}\n\n"

            heartbeat_count = 0
            max_heartbeats = 10  # 5 minutes of 30s heartbeats
            while heartbeat_count < max_heartbeats:
                yield ": heartbeat (connection alive)\n\n"
                await asyncio.sleep(30)
                heartbeat_count += 1

        except asyncio.CancelledError:
            # Client closed connection gracefully
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
