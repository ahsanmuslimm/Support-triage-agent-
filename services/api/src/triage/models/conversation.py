"""Conversation model."""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid


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
    subject: Optional[str] = None

    # Counts
    message_count: int = 0
    unread_count: int = 0

    # Classification (populated by triage)
    intent_primary: Optional[str] = None
    intent_secondary: Optional[str] = None
    confidence_score: Optional[float] = None

    # Resolution
    is_auto_resolved: bool = False
    resolution_category: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
