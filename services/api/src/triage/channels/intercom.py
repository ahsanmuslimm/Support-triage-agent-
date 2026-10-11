"""Intercom adapter implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from triage.channels.connector import (
    Attachment,
    AttachmentType,
    HelpdeskConnector,
    MessageNormalization,
    ReplyResult,
    TicketNormalization,
    TicketPriority,
    TicketStatus,
    ThreadEntry,
    TicketUpdateRequest,
)

log = structlog.get_logger()


class IntercomAdapter(HelpdeskConnector):
    """Intercom helpdesk adapter."""

    async def normalize_message(self, provider_message: Dict[str, Any]) -> MessageNormalization:
        """Normalize Intercom conversation message.

        Args:
            provider_message: Intercom message object.

        Returns:
            MessageNormalization: Normalized message.
        """
        # Extract author (contact or admin)
        author = provider_message.get("author", {})
        if author.get("type") == "contact":
            sender_id = author.get("id", "unknown")
            sender_email = author.get("email", "")
            sender_name = author.get("name", "")
        else:
            sender_id = author.get("id", "agent")
            sender_email = author.get("email", "")
            sender_name = author.get("name", "")

        # Extract message body
        body_parts = []
        if provider_message.get("body"):
            body_parts.append(provider_message["body"])

        # Handle custom attributes
        custom_attrs = provider_message.get("custom_attributes", {})
        metadata = {
            "conversation_id": provider_message.get("conversation_id", ""),
            "intercom_author_id": author.get("id"),
            "intercom_author_type": author.get("type"),
            "custom_attributes": custom_attrs,
        }

        # Parse attachments
        attachments = []
        for att in provider_message.get("attachments", []):
            attachments.append(
                Attachment(
                    filename=att.get("name", "attachment"),
                    content_type=att.get("content_type", "application/octet-stream"),
                    url=att.get("url", ""),
                    size_bytes=att.get("size", 0),
                    attachment_type=AttachmentType.DOCUMENT,
                )
            )

        return MessageNormalization(
            message_id=str(provider_message.get("id", "")),
            channel_message_id=str(provider_message.get("id", "")),
            body="\n".join(body_parts) or "",
            sender_id=sender_id,
            sender_email=sender_email or None,
            sender_name=sender_name or None,
            timestamp=datetime.fromisoformat(
                provider_message.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            thread_id=provider_message.get("conversation_id", ""),
            attachments=attachments,
            metadata=metadata,
        )

    async def normalize_ticket(self, provider_ticket: Dict[str, Any]) -> TicketNormalization:
        """Normalize Intercom conversation to ticket.

        Args:
            provider_ticket: Intercom conversation object.

        Returns:
            TicketNormalization: Normalized ticket.
        """
        # Map Intercom state to ticket status
        state = provider_ticket.get("state", "open")
        status_map = {
            "open": TicketStatus.OPEN,
            "closed": TicketStatus.CLOSED,
            "waiting_on_contact": TicketStatus.PENDING,
            "waiting_on_team": TicketStatus.ON_HOLD,
        }
        status = status_map.get(state, TicketStatus.OPEN)

        # Extract priority from custom attributes or default
        custom_attrs = provider_ticket.get("custom_attributes", {})
        priority_str = custom_attrs.get("priority", "p2").lower()
        priority_map = {"p0": TicketPriority.P0, "p1": TicketPriority.P1, "p2": TicketPriority.P2, "p3": TicketPriority.P3}
        priority = priority_map.get(priority_str, TicketPriority.P2)

        # Extract contact (requester)
        contact = provider_ticket.get("contact", {})
        requester_id = contact.get("id", "")
        requester_email = contact.get("email", "")
        requester_name = contact.get("name", "")

        # Extract assignee if present
        assignee_id = None
        if provider_ticket.get("assignee"):
            assignee_id = str(provider_ticket["assignee"].get("id"))

        # Build metadata
        metadata = {
            "conversation_id": provider_ticket.get("id", ""),
            "intercom_url": provider_ticket.get("url", ""),
            "source_type": provider_ticket.get("source", {}).get("type", ""),
        }

        return TicketNormalization(
            ticket_id=str(provider_ticket.get("id", "")),
            subject=f"Conversation {provider_ticket.get('id', '')[:8]}",
            description=provider_ticket.get("title", "") or "Intercom conversation",
            status=status,
            priority=priority,
            requester_id=requester_id,
            requester_email=requester_email or None,
            requester_name=requester_name or None,
            assignee_id=assignee_id,
            created_at=datetime.fromisoformat(
                provider_ticket.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                provider_ticket.get("updated_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            custom_fields=custom_attrs,
            tags=provider_ticket.get("tags", {}).get("data", []),
            category=custom_attrs.get("category"),
            segment=custom_attrs.get("segment"),
            metadata=metadata,
        )

    async def post_reply(
        self,
        ticket_id: str,
        message_body: str,
        attachments: Optional[List[Attachment]] = None,
    ) -> ReplyResult:
        """Post reply to Intercom conversation.

        Args:
            ticket_id: Intercom conversation ID.
            message_body: Reply text.
            attachments: Optional attachments.

        Returns:
            ReplyResult: Success indicator and provider message ID.
        """
        try:
            # In real implementation, POST to Intercom API
            # POST /conversations/{id}/reply
            log.info("post_reply", conversation_id=ticket_id, body_len=len(message_body))

            # Simulate provider message ID
            provider_message_id = f"msg_{ticket_id}_{datetime.utcnow().timestamp()}"

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
        """Update Intercom conversation.

        Args:
            ticket_id: Intercom conversation ID.
            request: Update request.

        Returns:
            bool: Success indicator.
        """
        try:
            log.info("update_ticket", conversation_id=ticket_id)

            # Build update payload
            updates = {}
            if request.status:
                status_map = {
                    TicketStatus.OPEN: "open",
                    TicketStatus.CLOSED: "closed",
                    TicketStatus.PENDING: "waiting_on_contact",
                    TicketStatus.ON_HOLD: "waiting_on_team",
                }
                updates["state"] = status_map.get(request.status, "open")

            if request.custom_fields:
                updates["custom_attributes"] = request.custom_fields

            if request.tags:
                updates["tags"] = request.tags

            # In real implementation, PATCH to Intercom API
            # PATCH /conversations/{id}

            return True
        except Exception as e:
            log.error("update_ticket_failed", error=str(e))
            return False

    async def fetch_thread_history(
        self,
        ticket_id: str,
        limit: int = 100,
    ) -> List[ThreadEntry]:
        """Fetch Intercom conversation history.

        Args:
            ticket_id: Intercom conversation ID.
            limit: Max messages.

        Returns:
            List[ThreadEntry]: Thread history.
        """
        try:
            log.info("fetch_thread_history", conversation_id=ticket_id, limit=limit)

            # In real implementation, GET from Intercom API
            # GET /conversations/{id}/parts

            thread = []
            # Simulate fetching 5 messages
            for i in range(min(5, limit)):
                thread.append(
                    ThreadEntry(
                        message_id=f"msg_{i}",
                        sender_id=f"sender_{i}",
                        sender_type="customer" if i % 2 == 0 else "agent",
                        body=f"Message {i} body",
                        timestamp=datetime.utcnow(),
                        attachments=[],
                        metadata={"sequence": i},
                    )
                )

            return thread
        except Exception as e:
            log.error("fetch_thread_history_failed", error=str(e))
            raise ValueError(f"Could not fetch thread history: {e}")
