"""Canonical message model for all channels."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import uuid


class ChannelType(str, Enum):
    """Supported channel types."""

    EMAIL = "email"
    WEB_CHAT = "web_chat"
    ZENDESK = "zendesk"
    INTERCOM = "intercom"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    API = "api"


class SenderType(str, Enum):
    """Message sender type."""

    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    """Message processing status."""

    INGESTED = "ingested"
    NORMALIZED = "normalized"
    ENCRYPTED = "encrypted"
    TRIAGE_PENDING = "triage_pending"
    TRIAGE_COMPLETE = "triage_complete"
    ARCHIVED = "archived"


class Attachment(BaseModel):
    """File attachment metadata."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    content_type: str
    size_bytes: int
    s3_key: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class CanonicalMessage(BaseModel):
    """Unified message model across all channels."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    conversation_id: str
    channel_id: str
    channel_type: ChannelType

    # Content
    body: str
    body_html: Optional[str] = None
    subject: Optional[str] = None

    # Sender
    sender_id: str
    sender_type: SenderType
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None

    # Threading/References
    parent_message_id: Optional[str] = None
    thread_id: Optional[str] = None

    # External identifiers
    provider_message_id: Optional[str] = None
    provider_timestamp: Optional[datetime] = None

    # Attachments
    attachments: List[Attachment] = Field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Idempotency
    idempotency_key: Optional[str] = None

    # Processing
    status: MessageStatus = MessageStatus.INGESTED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message body cannot be empty")
        return v.strip()


class MessageRequest(BaseModel):
    """API request to ingest a message."""

    body: str = Field(..., min_length=1, max_length=10_000)
    subject: Optional[str] = None
    channel_type: ChannelType
    sender_id: str
    sender_type: SenderType = SenderType.CUSTOMER
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    conversation_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    attachments: List[Attachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """API response after message ingestion."""

    id: str
    conversation_id: str
    status: MessageStatus
    idempotency_key: Optional[str] = None
    stream_url: Optional[str] = None
    created_at: datetime
