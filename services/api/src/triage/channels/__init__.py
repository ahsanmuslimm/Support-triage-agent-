"""Multi-channel connector framework."""

from triage.channels.connector import (
    Attachment,
    AttachmentType,
    HelpdeskConnector,
    MessageNormalization,
    ReplyResult,
    ThreadEntry,
    TicketNormalization,
    TicketPriority,
    TicketStatus,
    TicketUpdateRequest,
)
from triage.channels.freshdesk import FreshdeskAdapter
from triage.channels.intercom import IntercomAdapter
from triage.channels.whatsapp import WhatsAppAdapter
from triage.channels.zendesk import ZendeskAdapter

__all__ = [
    "Attachment",
    "AttachmentType",
    "FreshdeskAdapter",
    "HelpdeskConnector",
    "IntercomAdapter",
    "MessageNormalization",
    "ReplyResult",
    "ThreadEntry",
    "TicketNormalization",
    "TicketPriority",
    "TicketStatus",
    "TicketUpdateRequest",
    "WhatsAppAdapter",
    "ZendeskAdapter",
]
