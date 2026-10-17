"""Conversation model."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConversationStatus(str, Enum):
    """Conversation status states."""

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ConversationModel(BaseModel):
    """Conversation ORM and API model."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    customer_id: str
    channel_id: str

    # Status tracking
    status: ConversationStatus = ConversationStatus.OPEN
    priority: int = 0  # 0 = normal, 1 = high, -1 = low
    subject: str | None = None

    # Counts
    message_count: int = 0
    unread_count: int = 0

    # Classification (populated by triage)
    intent_primary: str | None = None
    intent_secondary: str | None = None
    confidence_score: float | None = None

    # Resolution
    is_auto_resolved: bool = False
    resolution_category: str | None = None

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: datetime | None = None
    resolved_at: datetime | None = None
