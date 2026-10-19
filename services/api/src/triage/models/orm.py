"""SQLAlchemy ORM models for the core persistence schema.

Mirrors the canonical Alembic migrations (0001/0003/0004/0008) in the
``triage`` schema. Composite primary keys ``(tenant_id, id)`` enforce
multi-tenancy at the row level; Row-Level Security policies additionally
gate access for non-owner roles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all triage ORM models."""


def _pk_uuid() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


class Tenant(Base):
    """Tenant (root of the multi-tenant hierarchy)."""

    __tablename__ = "tenants"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    id: Mapped[uuid.UUID] = _pk_uuid()
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Customer(Base):
    """Customer identity (pseudonymized; PII lives in the token vault)."""

    __tablename__ = "customers"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    external_id: Mapped[str | None] = mapped_column(String(255))
    email_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_hash: Mapped[str | None] = mapped_column(String(255))
    name_pseudonym: Mapped[str | None] = mapped_column(String(255))
    ltv_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'standard'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Conversation(Base):
    """A support conversation across channels."""

    __tablename__ = "conversations"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'open'"))
    priority: Mapped[str | None] = mapped_column(String(50), server_default=text("'normal'"))
    subject: Mapped[str | None] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    intent_primary: Mapped[str | None] = mapped_column(String(255))
    intent_secondary: Mapped[str | None] = mapped_column(String(255))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    is_auto_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """An ingested message (redacted plaintext + optional encrypted body)."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="idx_messages_tenant_idempotency_key",
        ),
        {"schema": "triage"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_encrypted: Mapped[dict | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(String(10))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    sender_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TriageRun(Base):
    """One execution of the triage agent graph over a message."""

    __tablename__ = "triage_runs"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("triage.messages.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    top_intent: Mapped[str | None] = mapped_column(String(100))
    intent_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    autonomy_level: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str | None] = mapped_column(String(50))
    tool_executed: Mapped[str | None] = mapped_column(String(100))
    tool_result: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExtractedEntity(Base):
    """Entity extracted from a message (PII values pseudonymized)."""

    __tablename__ = "extracted_entities"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("triage.messages.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    linked_id: Mapped[int | None] = mapped_column(BigInteger)
    is_pii: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    pseudonym: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEventORM(Base):
    """Transactional outbox row (published=NULL means pending delivery)."""

    __tablename__ = "outbox_events"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PiiToken(Base):
    """PII vault entry: SHA256 hash -> redaction token (+ encrypted value)."""

    __tablename__ = "pii_tokens"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    pii_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pii_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    encrypted_value: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyRecord(Base):
    """Processed-event ledger for exactly-once processing (S6.3)."""

    __tablename__ = "idempotency_records"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_first_attempt: Mapped[bool] = mapped_column(Boolean, default=True)


class IntentExample(Base):
    """Golden training example for the k-NN intent classifier."""

    __tablename__ = "intent_examples"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[uuid.UUID] = _pk_uuid()
    intent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    example_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_golden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IntentEmbedding(Base):
    """Per-intent centroid embedding (JSON array of 384 dims)."""

    __tablename__ = "intent_embeddings"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "triage"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage.tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    intent_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
