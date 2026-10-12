"""HelpdeskConnector protocol for multi-channel adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class AttachmentType(str, Enum):
    """Supported attachment types."""

    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"
    AUDIO = "audio"


class TicketStatus(str, Enum):
    """Ticket status enum."""

    OPEN = "open"
    PENDING = "pending"
    SOLVED = "solved"
    CLOSED = "closed"
    ON_HOLD = "on_hold"


class TicketPriority(str, Enum):
    """Ticket priority levels."""

    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


@dataclass
class Attachment:
    """Attachment metadata."""

    filename: str
    content_type: str
    url: str
    size_bytes: int
    attachment_type: AttachmentType = AttachmentType.DOCUMENT


@dataclass
class MessageNormalization:
    """Normalized message from external system."""

    message_id: str
    """Unique identifier in source system."""

    channel_message_id: str
    """Channel-specific message ID (e.g., WhatsApp message_id)."""

    body: str
    """Message text content."""

    sender_id: str
    """Sender identifier in source system."""

    sender_email: str | None = None
    """Sender email if available."""

    sender_name: str | None = None
    """Sender name."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    """Message creation time in source system."""

    thread_id: str = ""
    """Thread/conversation identifier."""

    attachments: list[Attachment] = field(default_factory=list)
    """Attached files."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Channel-specific metadata."""


@dataclass
class TicketNormalization:
    """Normalized ticket from external system."""

    ticket_id: str
    """Unique identifier in source system."""

    subject: str
    """Ticket subject/title."""

    description: str
    """Initial description."""

    status: TicketStatus
    """Current ticket status."""

    priority: TicketPriority
    """Ticket priority."""

    requester_id: str
    """Customer identifier."""

    requester_email: str | None = None
    """Customer email."""

    requester_name: str | None = None
    """Customer name."""

    assignee_id: str | None = None
    """Assigned agent ID."""

    created_at: datetime = field(default_factory=datetime.utcnow)
    """Ticket creation time."""

    updated_at: datetime = field(default_factory=datetime.utcnow)
    """Last update time."""

    custom_fields: dict[str, Any] = field(default_factory=dict)
    """Adapter-specific custom fields."""

    tags: list[str] = field(default_factory=list)
    """Ticket tags/labels."""

    category: str | None = None
    """Ticket category."""

    segment: str | None = None
    """Customer segment."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""


@dataclass
class ThreadEntry:
    """Single entry in a thread/ticket history."""

    message_id: str
    """Unique message ID."""

    sender_id: str
    """Sender identifier."""

    sender_type: str
    """'customer' or 'agent' or 'system'."""

    body: str
    """Message content."""

    timestamp: datetime
    """Message creation time."""

    attachments: list[Attachment] = field(default_factory=list)
    """Attached files."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Channel-specific metadata."""


@dataclass
class ReplyResult:
    """Result of posting a reply."""

    success: bool
    """Whether reply was posted successfully."""

    provider_message_id: str = ""
    """ID assigned by provider."""

    error: str | None = None
    """Error message if failed."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Response metadata."""


@dataclass
class TicketUpdateRequest:
    """Request to update ticket properties."""

    status: TicketStatus | None = None
    """New status."""

    priority: TicketPriority | None = None
    """New priority."""

    assignee_id: str | None = None
    """Assign to agent."""

    custom_fields: dict[str, Any] = field(default_factory=dict)
    """Custom field updates."""

    tags: list[str] = field(default_factory=list)
    """Tags to set."""

    category: str | None = None
    """New category."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional updates."""


class HelpdeskConnector(ABC):
    """Protocol for helpdesk system connectors."""

    def __init__(self, tenant_id: str, api_key: str, **config: Any) -> None:
        """Initialize connector.

        Args:
            tenant_id: Tenant identifier.
            api_key: API authentication key.
            **config: Additional configuration.
        """
        self.tenant_id = tenant_id
        self.api_key = api_key
        self.config = config

    @abstractmethod
    async def normalize_message(self, provider_message: dict[str, Any]) -> MessageNormalization:
        """Normalize message from provider format to canonical form.

        Args:
            provider_message: Message in provider's native format.

        Returns:
            MessageNormalization: Normalized message.

        Raises:
            ValueError: If message cannot be normalized.
        """

    @abstractmethod
    async def normalize_ticket(self, provider_ticket: dict[str, Any]) -> TicketNormalization:
        """Normalize ticket from provider format.

        Args:
            provider_ticket: Ticket in provider's native format.

        Returns:
            TicketNormalization: Normalized ticket.

        Raises:
            ValueError: If ticket cannot be normalized.
        """

    @abstractmethod
    async def post_reply(
        self,
        ticket_id: str,
        message_body: str,
        attachments: list[Attachment] | None = None,
    ) -> ReplyResult:
        """Post a reply to a ticket.

        Args:
            ticket_id: Provider ticket ID.
            message_body: Reply text.
            attachments: Optional file attachments.

        Returns:
            ReplyResult: Success/failure with provider message ID.
        """

    @abstractmethod
    async def update_ticket(
        self,
        ticket_id: str,
        request: TicketUpdateRequest,
    ) -> bool:
        """Update ticket properties.

        Args:
            ticket_id: Provider ticket ID.
            request: Update request.

        Returns:
            bool: True if successful.
        """

    @abstractmethod
    async def fetch_thread_history(
        self,
        ticket_id: str,
        limit: int = 100,
    ) -> list[ThreadEntry]:
        """Fetch complete thread/ticket history.

        Args:
            ticket_id: Provider ticket ID.
            limit: Maximum entries to fetch.

        Returns:
            List[ThreadEntry]: Thread history in chronological order.

        Raises:
            ValueError: If ticket not found.
        """
