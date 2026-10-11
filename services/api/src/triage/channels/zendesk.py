"""Zendesk adapter implementation with advanced routing."""

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


class ZendeskAdapter(HelpdeskConnector):
    """Zendesk helpdesk adapter with sidebar + advanced routing."""

    async def normalize_message(self, provider_message: Dict[str, Any]) -> MessageNormalization:
        """Normalize Zendesk comment.

        Args:
            provider_message: Zendesk comment object.

        Returns:
            MessageNormalization: Normalized message.
        """
        # Extract body
        body = provider_message.get("body", "")
        if provider_message.get("html_body"):
            body = provider_message["html_body"]

        # Extract author
        author_id = provider_message.get("author_id", "")
        author_email = ""
        author_name = ""

        metadata = {
            "comment_id": provider_message.get("id", ""),
            "public": provider_message.get("public", False),
            "author_id": author_id,
        }

        # Parse attachments
        attachments = []
        for att in provider_message.get("attachments", []):
            attachments.append(
                Attachment(
                    filename=att.get("filename", "attachment"),
                    content_type=att.get("content_type", "application/octet-stream"),
                    url=att.get("content_url", ""),
                    size_bytes=att.get("size", 0),
                    attachment_type=AttachmentType.DOCUMENT,
                )
            )

        return MessageNormalization(
            message_id=str(provider_message.get("id", "")),
            channel_message_id=str(provider_message.get("id", "")),
            body=body,
            sender_id=author_id,
            sender_email=author_email or None,
            sender_name=author_name or None,
            timestamp=datetime.fromisoformat(
                provider_message.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            thread_id=provider_message.get("ticket_id", ""),
            attachments=attachments,
            metadata=metadata,
        )

    async def normalize_ticket(self, provider_ticket: Dict[str, Any]) -> TicketNormalization:
        """Normalize Zendesk ticket.

        Args:
            provider_ticket: Zendesk ticket object.

        Returns:
            TicketNormalization: Normalized ticket.
        """
        # Map Zendesk status
        status_map = {
            "new": TicketStatus.OPEN,
            "open": TicketStatus.OPEN,
            "pending": TicketStatus.PENDING,
            "hold": TicketStatus.ON_HOLD,
            "solved": TicketStatus.SOLVED,
            "closed": TicketStatus.CLOSED,
        }
        status = status_map.get(provider_ticket.get("status", "open"), TicketStatus.OPEN)

        # Map Zendesk priority
        priority_map = {
            "low": TicketPriority.P3,
            "normal": TicketPriority.P2,
            "high": TicketPriority.P1,
            "urgent": TicketPriority.P0,
        }
        priority = priority_map.get(provider_ticket.get("priority", "normal"), TicketPriority.P2)

        # Extract custom fields for routing hint
        custom_fields = {}
        for field in provider_ticket.get("custom_fields", []):
            custom_fields[field.get("id")] = field.get("value")

        metadata = {
            "ticket_id": provider_ticket.get("id", ""),
            "zendesk_url": provider_ticket.get("url", ""),
            "group_id": provider_ticket.get("group_id"),
            "organization_id": provider_ticket.get("organization_id"),
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
            assignee_id=str(provider_ticket.get("assignee_id")) if provider_ticket.get("assignee_id") else None,
            created_at=datetime.fromisoformat(
                provider_ticket.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                provider_ticket.get("updated_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            custom_fields=custom_fields,
            tags=provider_ticket.get("tags", []),
            category=custom_fields.get("category"),
            segment=custom_fields.get("segment"),
            metadata=metadata,
        )

    async def post_reply(
        self,
        ticket_id: str,
        message_body: str,
        attachments: Optional[List[Attachment]] = None,
    ) -> ReplyResult:
        """Post comment to Zendesk ticket.

        Args:
            ticket_id: Zendesk ticket ID.
            message_body: Comment text.
            attachments: Optional attachments.

        Returns:
            ReplyResult: Success indicator and provider message ID.
        """
        try:
            log.info("post_reply", ticket_id=ticket_id, body_len=len(message_body))

            # In real implementation, POST to Zendesk API
            # POST /tickets/{id}/comments

            provider_message_id = f"comment_{ticket_id}_{datetime.utcnow().timestamp()}"

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
        """Update Zendesk ticket.

        Args:
            ticket_id: Zendesk ticket ID.
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
                    TicketStatus.OPEN: "open",
                    TicketStatus.PENDING: "pending",
                    TicketStatus.ON_HOLD: "hold",
                    TicketStatus.SOLVED: "solved",
                    TicketStatus.CLOSED: "closed",
                }
                updates["status"] = status_map.get(request.status, "open")

            if request.priority:
                priority_map = {
                    TicketPriority.P3: "low",
                    TicketPriority.P2: "normal",
                    TicketPriority.P1: "high",
                    TicketPriority.P0: "urgent",
                }
                updates["priority"] = priority_map.get(request.priority, "normal")

            if request.assignee_id:
                updates["assignee_id"] = request.assignee_id

            if request.tags:
                updates["tags"] = request.tags

            if request.custom_fields:
                # Convert to Zendesk custom_fields array format
                custom_fields_arr = []
                for field_id, value in request.custom_fields.items():
                    custom_fields_arr.append({"id": field_id, "value": value})
                updates["custom_fields"] = custom_fields_arr

            # In real implementation, PUT to Zendesk API
            # PUT /tickets/{id}

            return True
        except Exception as e:
            log.error("update_ticket_failed", error=str(e))
            return False

    async def fetch_thread_history(
        self,
        ticket_id: str,
        limit: int = 100,
    ) -> List[ThreadEntry]:
        """Fetch Zendesk ticket comments.

        Args:
            ticket_id: Zendesk ticket ID.
            limit: Max comments.

        Returns:
            List[ThreadEntry]: Thread history.
        """
        try:
            log.info("fetch_thread_history", ticket_id=ticket_id, limit=limit)

            # In real implementation, GET from Zendesk API
            # GET /tickets/{id}/comments

            thread = []
            # Simulate fetching 5 comments
            for i in range(min(5, limit)):
                thread.append(
                    ThreadEntry(
                        message_id=f"comment_{i}",
                        sender_id=f"user_{i}",
                        sender_type="customer" if i % 2 == 0 else "agent",
                        body=f"Comment {i} body",
                        timestamp=datetime.utcnow(),
                        attachments=[],
                        metadata={"public": True},
                    )
                )

            return thread
        except Exception as e:
            log.error("fetch_thread_history_failed", error=str(e))
            raise ValueError(f"Could not fetch thread history: {e}")

    def get_routing_sidebar_config(self, ticket: TicketNormalization) -> Dict[str, Any]:
        """Build sidebar configuration for advanced routing UI.

        Args:
            ticket: Normalized ticket.

        Returns:
            Dict[str, Any]: Sidebar config with routing suggestions.
        """
        return {
            "ticket_id": ticket.ticket_id,
            "suggested_assignees": self._suggest_assignees(ticket),
            "recommended_status": self._recommend_status(ticket),
            "routing_hints": self._generate_routing_hints(ticket),
        }

    def _suggest_assignees(self, ticket: TicketNormalization) -> List[Dict[str, Any]]:
        """Suggest appropriate assignees based on ticket properties."""
        # Placeholder for agent skill matching
        return [
            {"agent_id": "agent_1", "skill": "billing", "load": 0.5},
            {"agent_id": "agent_2", "skill": "technical", "load": 0.7},
        ]

    def _recommend_status(self, ticket: TicketNormalization) -> str:
        """Recommend next status based on ticket history."""
        if ticket.status == TicketStatus.OPEN:
            return "pending"
        return ticket.status.value

    def _generate_routing_hints(self, ticket: TicketNormalization) -> Dict[str, str]:
        """Generate routing hints for agent context."""
        return {
            "priority_hint": f"Customer is {ticket.priority.value} priority",
            "category_hint": ticket.category or "Uncategorized",
            "segment_hint": ticket.segment or "Standard",
        }
