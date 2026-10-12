"""Freshdesk adapter implementation."""

from datetime import datetime
from typing import Any

import structlog

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

log = structlog.get_logger()


class FreshdeskAdapter(HelpdeskConnector):
    """Freshdesk helpdesk adapter."""

    async def normalize_message(self, provider_message: dict[str, Any]) -> MessageNormalization:
        """Normalize Freshdesk conversation note/reply.

        Args:
            provider_message: Freshdesk note/reply object.

        Returns:
            MessageNormalization: Normalized message.
        """
        # Extract body from note_type or body_html
        body = provider_message.get("body", "")
        if provider_message.get("body_html"):
            # Strip HTML tags for body field
            body = provider_message["body_html"]

        # Determine sender type
        sender_id = provider_message.get("user_id", "")
        sender_name = provider_message.get("user_name", "")
        sender_email = provider_message.get("user_email", "")

        # Parse attachments
        attachments = []
        for att in provider_message.get("attachments", []):
            attachments.append(
                Attachment(
                    filename=att.get("name", "attachment"),
                    content_type=att.get("content_type", "application/octet-stream"),
                    url=att.get("attachment_url", ""),
                    size_bytes=att.get("size", 0),
                    attachment_type=AttachmentType.DOCUMENT,
                )
            )

        metadata = {
            "note_type": provider_message.get("note_type", ""),
            "freshdesk_id": provider_message.get("id", ""),
            "incoming": provider_message.get("incoming", False),
        }

        return MessageNormalization(
            message_id=str(provider_message.get("id", "")),
            channel_message_id=str(provider_message.get("id", "")),
            body=body,
            sender_id=sender_id,
            sender_email=sender_email or None,
            sender_name=sender_name or None,
            timestamp=datetime.fromisoformat(
                provider_message.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            thread_id=provider_message.get("ticket_id", ""),
            attachments=attachments,
            metadata=metadata,
        )

    async def normalize_ticket(self, provider_ticket: dict[str, Any]) -> TicketNormalization:
        """Normalize Freshdesk ticket.

        Args:
            provider_ticket: Freshdesk ticket object.

        Returns:
            TicketNormalization: Normalized ticket.
        """
        # Map Freshdesk status to ticket status
        status_map = {
            2: TicketStatus.OPEN,
            3: TicketStatus.PENDING,
            4: TicketStatus.SOLVED,
            5: TicketStatus.CLOSED,
        }
        status = status_map.get(provider_ticket.get("status", 2), TicketStatus.OPEN)

        # Map Freshdesk priority to ticket priority
        priority_map = {
            1: TicketPriority.P3,
            2: TicketPriority.P2,
            3: TicketPriority.P1,
            4: TicketPriority.P0,
        }
        priority = priority_map.get(provider_ticket.get("priority", 2), TicketPriority.P2)

        # Extract custom fields
        custom_fields = provider_ticket.get("custom_fields", {})
        category = custom_fields.get("category")
        segment = custom_fields.get("segment")

        metadata = {
            "ticket_id": provider_ticket.get("id", ""),
            "freshdesk_url": provider_ticket.get("url", ""),
            "group_id": provider_ticket.get("group_id"),
        }

        return TicketNormalization(
            ticket_id=str(provider_ticket.get("id", "")),
            subject=provider_ticket.get("subject", ""),
            description=provider_ticket.get("description", ""),
            status=status,
            priority=priority,
            requester_id=str(provider_ticket.get("requester_id", "")),
            requester_email=provider_ticket.get("requester", {}).get("email"),
            requester_name=provider_ticket.get("requester", {}).get("name"),
            assignee_id=str(provider_ticket.get("responder_id")) if provider_ticket.get("responder_id") else None,
            created_at=datetime.fromisoformat(
                provider_ticket.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                provider_ticket.get("updated_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            custom_fields=custom_fields,
            tags=provider_ticket.get("tags", []),
            category=category,
            segment=segment,
            metadata=metadata,
        )

    async def post_reply(
        self,
        ticket_id: str,
        message_body: str,
        attachments: list[Attachment] | None = None,
    ) -> ReplyResult:
        """Post reply to Freshdesk ticket.

        Args:
            ticket_id: Freshdesk ticket ID.
            message_body: Reply text.
            attachments: Optional attachments.

        Returns:
            ReplyResult: Success indicator and provider message ID.
        """
        try:
            log.info("post_reply", ticket_id=ticket_id, body_len=len(message_body))

            # In real implementation, POST to Freshdesk API
            # POST /tickets/{id}/notes

            provider_message_id = f"note_{ticket_id}_{datetime.utcnow().timestamp()}"

            return ReplyResult(
                success=True,
                provider_message_id=provider_message_id,
                metadata={"message_body_chars": len(message_body), "attachments_count": len(attachments or [])},
            )
        except Exception as e:
            log.error("post_reply_failed", error=str(e))
            return ReplyResult(success=False, error=str(e))

    async def update_ticket(
        self,
        ticket_id: str,
        request: TicketUpdateRequest,
    ) -> bool:
        """Update Freshdesk ticket.

        Args:
            ticket_id: Freshdesk ticket ID.
            request: Update request.

        Returns:
            bool: Success indicator.
        """
        try:
            log.info("update_ticket", ticket_id=ticket_id)

            # Build update payload
            updates = {}

            if request.status:
                status_map = {
                    TicketStatus.OPEN: 2,
                    TicketStatus.PENDING: 3,
                    TicketStatus.SOLVED: 4,
                    TicketStatus.CLOSED: 5,
                }
                updates["status"] = status_map.get(request.status, 2)

            if request.priority:
                priority_map = {
                    TicketPriority.P3: 1,
                    TicketPriority.P2: 2,
                    TicketPriority.P1: 3,
                    TicketPriority.P0: 4,
                }
                updates["priority"] = priority_map.get(request.priority, 2)

            if request.assignee_id:
                updates["responder_id"] = request.assignee_id

            if request.custom_fields:
                updates["custom_fields"] = request.custom_fields

            if request.tags:
                updates["tags"] = request.tags

            # In real implementation, PUT to Freshdesk API
            # PUT /tickets/{id}

            return True
        except Exception as e:
            log.error("update_ticket_failed", error=str(e))
            return False

    async def fetch_thread_history(
        self,
        ticket_id: str,
        limit: int = 100,
    ) -> list[ThreadEntry]:
        """Fetch Freshdesk ticket history.

        Args:
            ticket_id: Freshdesk ticket ID.
            limit: Max entries.

        Returns:
            List[ThreadEntry]: Thread history.
        """
        try:
            log.info("fetch_thread_history", ticket_id=ticket_id, limit=limit)

            # In real implementation, GET from Freshdesk API
            # GET /tickets/{id}/notes

            thread = []
            # Simulate fetching 5 notes
            for i in range(min(5, limit)):
                thread.append(
                    ThreadEntry(
                        message_id=f"note_{i}",
                        sender_id=f"user_{i}",
                        sender_type="customer" if i % 2 == 0 else "agent",
                        body=f"Note {i} body",
                        timestamp=datetime.utcnow(),
                        attachments=[],
                        metadata={"note_type": "reply"},
                    )
                )

            return thread
        except Exception as e:
            log.error("fetch_thread_history_failed", error=str(e))
            raise ValueError(f"Could not fetch thread history: {e}")
