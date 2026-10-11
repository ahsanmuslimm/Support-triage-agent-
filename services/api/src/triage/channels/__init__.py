"""Multi-channel connector framework."""

from triage.channels.connector import (
    HelpdeskConnector,
    MessageNormalization,
    TicketNormalization,
    ThreadEntry,
    ReplyResult,
    TicketUpdateRequest,
    Attachment,
    AttachmentType,
    TicketStatus,
    TicketPriority,
)
from triage.channels.intercom import IntercomAdapter
from triage.channels.freshdesk import FreshdeskAdapter
from triage.channels.zendesk import ZendeskAdapter
from triage.channels.whatsapp import WhatsAppAdapter

__all__ = [
    "HelpdeskConnector",
    "MessageNormalization",
    "TicketNormalization",
    "ThreadEntry",
    "ReplyResult",
    "TicketUpdateRequest",
    "Attachment",
    "AttachmentType",
    "TicketStatus",
    "TicketPriority",
    "IntercomAdapter",
    "FreshdeskAdapter",
    "ZendeskAdapter",
    "WhatsAppAdapter",
]
