"""Conversation endpoints (DB-backed)."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ...db import SessionDep, TenantDep, stable_uuid
from ...models.conversation import ConversationModel, ConversationStatus
from ...models.orm import Conversation as ConversationORM

router = APIRouter()

_PRIORITY_TO_INT = {"low": -1, "normal": 0, "high": 1}


def _to_model(orm: ConversationORM) -> ConversationModel:
    """Map an ORM row to the API model."""
    return ConversationModel(
        id=str(orm.id),
        tenant_id=str(orm.tenant_id),
        customer_id=str(orm.customer_id),
        channel_id=orm.channel_id or "web_chat",
        status=ConversationStatus(orm.status),
        priority=_PRIORITY_TO_INT.get(orm.priority or "normal", 0),
        subject=orm.subject,
        message_count=orm.message_count,
        unread_count=orm.unread_count,
        intent_primary=orm.intent_primary,
        intent_secondary=orm.intent_secondary,
        confidence_score=orm.confidence_score,
        is_auto_resolved=orm.is_auto_resolved,
        metadata=orm.metadata_json or {},
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        last_message_at=orm.last_message_at,
        resolved_at=orm.resolved_at,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    session: SessionDep,
    tenant_id: TenantDep,
) -> ConversationModel:
    """Get conversation details."""
    conv_uuid = stable_uuid(conversation_id)
    conversation = await session.get(ConversationORM, (tenant_id, conv_uuid))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _to_model(conversation)


@router.get("/conversations", response_model=list[ConversationModel])
async def list_conversations(
    session: SessionDep,
    tenant_id: TenantDep,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationModel]:
    """List conversations for tenant (most recent activity first)."""
    query = (
        select(ConversationORM)
        .where(ConversationORM.tenant_id == tenant_id)
        .order_by(
            ConversationORM.last_message_at.desc().nulls_last(),
            ConversationORM.created_at.desc(),
        )
    )
    if status is not None:
        query = query.where(ConversationORM.status == status)
    query = query.limit(min(limit, 200)).offset(offset)

    result = await session.execute(query)
    return [_to_model(orm) for orm in result.scalars().all()]


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    session: SessionDep,
    tenant_id: TenantDep,
    status: ConversationStatus | None = None,
) -> ConversationModel:
    """Update conversation status (e.g. resolve or escalate)."""
    if status is None:
        raise HTTPException(status_code=400, detail="status query parameter required")

    conv_uuid = stable_uuid(conversation_id)
    conversation = await session.get(ConversationORM, (tenant_id, conv_uuid))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.status = status.value
    conversation.updated_at = datetime.now(UTC)
    if status == ConversationStatus.RESOLVED:
        conversation.resolved_at = conversation.updated_at

    await session.commit()
    return _to_model(conversation)
