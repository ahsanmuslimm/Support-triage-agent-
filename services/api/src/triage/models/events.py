"""Outbox event models for transactional publishing."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class OutboxEvent(BaseModel):
    """Transactional outbox event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    aggregate_type: str  # "message", "conversation", etc.
    aggregate_id: str
    event_type: str  # "message.ingested", "conversation.created", etc.
    payload: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None
