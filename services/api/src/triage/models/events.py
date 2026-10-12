"""Outbox event models for transactional publishing."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OutboxEvent(BaseModel):
    """Transactional outbox event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    aggregate_type: str  # "message", "conversation", etc.
    aggregate_id: str
    event_type: str  # "message.ingested", "conversation.created", etc.
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: datetime | None = None
    retry_count: int = 0
    error_message: str | None = None
