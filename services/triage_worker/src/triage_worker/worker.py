"""Outbox-polling loop for the triage worker."""

import asyncio
import os
import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from triage.db import create_engine
from triage.models.orm import (
    Conversation,
    Customer,
    OutboxEventORM,
    TriageRun,
)
from triage.models.orm import (
    Message as MessageORM,
)

from .processor import triage_text

log = structlog.get_logger()

POLL_INTERVAL = float(os.environ.get("TRIAGE_POLL_INTERVAL", "1.0"))
BATCH_SIZE = int(os.environ.get("TRIAGE_BATCH_SIZE", "10"))
MAX_FAILURES = 3

_failures: dict[tuple[uuid.UUID, uuid.UUID], int] = {}


async def handle_event(session: AsyncSession, event: OutboxEventORM) -> bool:
    """Triage the message referenced by a ``message.ingested`` event.

    Persists a TriageRun and updates the conversation's intent fields.
    Returns False when the referenced message no longer exists.
    """
    started = time.perf_counter()
    message = await session.get(MessageORM, (event.tenant_id, event.aggregate_id))
    if message is None:
        log.error("triage_message_missing", event_id=str(event.id), tenant_id=str(event.tenant_id))
        return False

    conversation = await session.get(Conversation, (event.tenant_id, message.conversation_id))
    customer_tier = "standard"
    if conversation is not None:
        customer = await session.get(Customer, (event.tenant_id, conversation.customer_id))
        if customer is not None:
            customer_tier = customer.tier

    outcome = triage_text(
        message.body,
        channel=message.channel_type,
        customer_tier=customer_tier,
        is_repeat_customer=bool(conversation and conversation.message_count > 1),
    )

    latency_ms = (time.perf_counter() - started) * 1000
    session.add(
        TriageRun(
            tenant_id=event.tenant_id,
            message_id=message.id,
            conversation_id=message.conversation_id,
            top_intent=outcome.top_intent,
            intent_confidence=round(outcome.top_confidence, 2),
            autonomy_level=outcome.autonomy_level,
            action=outcome.action,
            tool_result={"rule": outcome.rule_triggered, "fallback_used": outcome.fallback_used},
            latency_ms=latency_ms,
            reasoning=[
                {
                    "stage": "intent",
                    "top_intent": outcome.top_intent,
                    "confidence": outcome.top_confidence,
                },
                {
                    "stage": "decision",
                    "reason": outcome.reason,
                    "autonomy_level": outcome.autonomy_level,
                },
            ],
            status="completed",
        )
    )
    if conversation is not None:
        conversation.intent_primary = outcome.top_intent
        conversation.confidence_score = outcome.top_confidence

    log.info(
        "message_triaged",
        message_id=str(message.id),
        top_intent=outcome.top_intent,
        autonomy_level=outcome.autonomy_level,
        action=outcome.action,
    )
    return True


async def process_batch(factory: async_sessionmaker[AsyncSession]) -> int:
    """Claim and process one batch of unpublished outbox events."""
    async with factory() as session:
        result = await session.execute(
            select(OutboxEventORM)
            .where(
                OutboxEventORM.published_at.is_(None),
                OutboxEventORM.event_type == "message.ingested",
            )
            .order_by(OutboxEventORM.created_at)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())
        processed = 0
        for event in events:
            key = (event.tenant_id, event.id)
            if _failures.get(key, 0) >= MAX_FAILURES:
                continue
            try:
                await handle_event(session, event)
                event.published_at = datetime.now(UTC)
                await session.commit()
                processed += 1
            except Exception as e:
                await session.rollback()
                _failures[key] = _failures.get(key, 0) + 1
                log.warning(
                    "triage_event_failed",
                    event_id=str(event.id),
                    tenant_id=str(event.tenant_id),
                    failures=_failures[key],
                    error=str(e),
                )
        return processed


async def run_forever() -> None:
    """Main worker loop: poll the outbox and triage new messages."""
    engine = create_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    log.info("triage_worker_started", poll_interval=POLL_INTERVAL, batch_size=BATCH_SIZE)
    try:
        while True:
            try:
                await process_batch(factory)
            except Exception:
                log.exception("triage_poll_error")
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        await engine.dispose()
