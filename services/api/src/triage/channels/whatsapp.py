"""WhatsApp adapter with Meta Cloud API and 24h window tracking."""

from datetime import datetime, timedelta
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


class WhatsAppWindow:
    """Tracks 24-hour messaging window for customer contact."""

    def __init__(self, last_customer_message_timestamp: datetime | None = None):
        """Initialize window tracker.

        Args:
            last_customer_message_timestamp: Last inbound message timestamp.
        """
        self.last_customer_message_timestamp = last_customer_message_timestamp or datetime.utcnow()

    def is_within_window(self) -> bool:
        """Check if within 24-hour window.

        Returns:
            bool: True if current time is within 24 hours of last customer message.
        """
        if not self.last_customer_message_timestamp:
            return False
        elapsed = datetime.utcnow() - self.last_customer_message_timestamp
        return elapsed < timedelta(hours=24)

    def calculate_time_remaining(self) -> timedelta:
        """Calculate remaining time in 24-hour window.

        Returns:
            timedelta: Time remaining until window expires. Negative if expired.
        """
        if not self.last_customer_message_timestamp:
            return timedelta(0)
        window_deadline = self.last_customer_message_timestamp + timedelta(hours=24)
        return window_deadline - datetime.utcnow()

    def requires_template(self) -> bool:
        """Check if message requires HSM template.

        Returns:
            bool: True if outside 24h window (requires template).
        """
        return not self.is_within_window()


class WhatsAppTemplate:
    """Pre-built HSM template for cost-effective messaging."""

    def __init__(self, template_id: str, name: str, category: str, language: str = "en"):
        """Initialize template.

        Args:
            template_id: Meta template ID.
            name: Template name.
            category: Template category (e.g., 'order_status', 'account_alert').
            language: Language code.
        """
        self.template_id = template_id
        self.name = name
        self.category = category
        self.language = language
        self.credit_cost = 0.5  # HSM costs 0.5 credits vs 1 for regular message

    def matches_context(self, context: dict[str, Any]) -> bool:
        """Check if template matches current message context.

        Args:
            context: Message context (intent, entity, etc).

        Returns:
            bool: True if template is appropriate.
        """
        # Match template category to context
        return context.get("intent") == self.category or context.get("category") == self.category


class WhatsAppTemplateLibrary:
    """Library of pre-approved WhatsApp templates."""

    def __init__(self):
        """Initialize template library."""
        self.templates = [
            WhatsAppTemplate("order_status_001", "order_status", "order_status", "en"),
            WhatsAppTemplate("account_alert_001", "account_alert", "account_alert", "en"),
            WhatsAppTemplate("password_reset_001", "password_reset", "password_reset", "en"),
            WhatsAppTemplate("callback_request_001", "callback_request", "callback_request", "en"),
        ]

    def find_template(self, context: dict[str, Any]) -> WhatsAppTemplate | None:
        """Find best-matching template for context.

        Args:
            context: Message context.

        Returns:
            Optional[WhatsAppTemplate]: Matching template or None.
        """
        for template in self.templates:
            if template.matches_context(context):
                return template
        return None

    def get_all_templates(self) -> list[WhatsAppTemplate]:
        """Get all available templates.

        Returns:
            List[WhatsAppTemplate]: All templates.
        """
        return self.templates


class WhatsAppAdapter(HelpdeskConnector):
    """WhatsApp adapter using Meta Cloud API."""

    def __init__(self, tenant_id: str, api_key: str, **config: Any) -> None:
        """Initialize WhatsApp adapter.

        Args:
            tenant_id: Tenant ID.
            api_key: Meta API key.
            **config: Additional config (phone_number_id, etc).
        """
        super().__init__(tenant_id, api_key, **config)
        self.phone_number_id = config.get("phone_number_id", "")
        self.template_library = WhatsAppTemplateLibrary()
        self.windows: dict[str, WhatsAppWindow] = {}  # phone_number -> Window

    async def normalize_message(self, provider_message: dict[str, Any]) -> MessageNormalization:
        """Normalize WhatsApp message from Meta Cloud API.

        Args:
            provider_message: Meta API message object.

        Returns:
            MessageNormalization: Normalized message.
        """
        # Extract message content
        message_body = provider_message.get("text", {}).get("body", "")

        # Extract media
        attachments = []
        if provider_message.get("image"):
            media = provider_message["image"]
            attachments.append(
                Attachment(
                    filename=media.get("caption", "image.jpg"),
                    content_type="image/jpeg",
                    url=media.get("link", ""),
                    size_bytes=0,
                    attachment_type=AttachmentType.IMAGE,
                )
            )
        elif provider_message.get("document"):
            media = provider_message["document"]
            attachments.append(
                Attachment(
                    filename=media.get("caption", "document.pdf"),
                    content_type=media.get("mime_type", "application/pdf"),
                    url=media.get("link", ""),
                    size_bytes=0,
                    attachment_type=AttachmentType.DOCUMENT,
                )
            )
        elif provider_message.get("video"):
            media = provider_message["video"]
            attachments.append(
                Attachment(
                    filename=media.get("caption", "video.mp4"),
                    content_type="video/mp4",
                    url=media.get("link", ""),
                    size_bytes=0,
                    attachment_type=AttachmentType.VIDEO,
                )
            )

        # Normalize phone number
        sender_id = self._normalize_phone(provider_message.get("from", ""))
        timestamp = datetime.fromtimestamp(int(provider_message.get("timestamp", 0)))

        # Update 24h window for this customer
        self.windows[sender_id] = WhatsAppWindow(timestamp)

        metadata = {
            "message_id": provider_message.get("id", ""),
            "type": provider_message.get("type", "text"),
            "in_24h_window": True,
            "timestamp_unix": provider_message.get("timestamp", 0),
        }

        return MessageNormalization(
            message_id=str(provider_message.get("id", "")),
            channel_message_id=str(provider_message.get("id", "")),
            body=message_body,
            sender_id=sender_id,
            sender_email=None,
            sender_name=provider_message.get("profile", {}).get("name"),
            timestamp=timestamp,
            thread_id=sender_id,  # Use phone number as thread ID
            attachments=attachments,
            metadata=metadata,
        )

    async def normalize_ticket(self, provider_ticket: dict[str, Any]) -> TicketNormalization:
        """Normalize WhatsApp conversation to ticket.

        Args:
            provider_ticket: WhatsApp conversation object.

        Returns:
            TicketNormalization: Normalized ticket.
        """
        phone_number = self._normalize_phone(provider_ticket.get("phone_number", ""))

        metadata = {
            "phone_number": phone_number,
            "conversation_id": provider_ticket.get("id", ""),
            "in_24h_window": self._is_in_window(phone_number),
            "business_account_id": self.phone_number_id,
        }

        return TicketNormalization(
            ticket_id=phone_number,
            subject=f"WhatsApp Conversation: {phone_number}",
            description=provider_ticket.get("status", "New conversation"),
            status=TicketStatus.OPEN,
            priority=TicketPriority.P2,
            requester_id=phone_number,
            requester_email=None,
            requester_name=provider_ticket.get("profile", {}).get("name"),
            assignee_id=provider_ticket.get("assigned_agent_id"),
            created_at=datetime.fromtimestamp(int(provider_ticket.get("created_at", 0))),
            updated_at=datetime.utcnow(),
            custom_fields={},
            tags=[],
            metadata=metadata,
        )

    async def post_reply(
        self,
        ticket_id: str,
        message_body: str,
        attachments: list[Attachment] | None = None,
    ) -> ReplyResult:
        """Post reply to WhatsApp conversation.

        Args:
            ticket_id: Phone number (ticket_id).
            message_body: Reply text.
            attachments: Optional attachments.

        Returns:
            ReplyResult: Success indicator and provider message ID.
        """
        try:
            # Check 24-hour window
            in_window = self._is_in_window(ticket_id)

            # Check if template is needed
            context = {"intent": "general"}
            template = self.template_library.find_template(context) if not in_window else None

            if not in_window and not template:
                # Fallback to SMS if no suitable template
                log.warning("fallback_to_sms", phone=ticket_id)
                return ReplyResult(
                    success=False,
                    error="24h window expired and no suitable template found. Fallback to SMS.",
                    metadata={"fallback_method": "sms"},
                )

            log.info(
                "post_reply",
                phone=ticket_id,
                in_window=in_window,
                using_template=template is not None,
            )

            # In real implementation, POST to Meta Cloud API
            # POST /v18.0/{phone_number_id}/messages

            provider_message_id = f"wamsg_{ticket_id}_{datetime.utcnow().timestamp()}"

            return ReplyResult(
                success=True,
                provider_message_id=provider_message_id,
                metadata={
                    "message_body_chars": len(message_body),
                    "attachments_count": len(attachments or []),
                    "in_24h_window": in_window,
                    "template_used": template is not None,
                    "credit_cost": 0.5 if template else 1.0,
                },
            )
        except Exception as e:
            log.error("post_reply_failed", error=str(e))
            return ReplyResult(success=False, error=str(e))

    async def update_ticket(
        self,
        ticket_id: str,
        request: TicketUpdateRequest,
    ) -> bool:
        """Update WhatsApp conversation.

        Args:
            ticket_id: Phone number.
            request: Update request.

        Returns:
            bool: Success indicator.
        """
        try:
            log.info("update_ticket", phone=ticket_id)

            # In real implementation, update conversation metadata
            # Via Meta Cloud API

            return True
        except Exception as e:
            log.error("update_ticket_failed", error=str(e))
            return False

    async def fetch_thread_history(
        self,
        ticket_id: str,
        limit: int = 100,
    ) -> list[ThreadEntry]:
        """Fetch WhatsApp conversation history.

        Args:
            ticket_id: Phone number.
            limit: Max messages.

        Returns:
            List[ThreadEntry]: Thread history.
        """
        try:
            log.info("fetch_thread_history", phone=ticket_id, limit=limit)

            # In real implementation, GET from Meta Cloud API
            # GET /v18.0/{phone_number_id}/messages

            thread = []
            # Simulate fetching messages
            for i in range(min(5, limit)):
                thread.append(
                    ThreadEntry(
                        message_id=f"msg_{i}",
                        sender_id=ticket_id if i % 2 == 0 else "agent",
                        sender_type="customer" if i % 2 == 0 else "agent",
                        body=f"WhatsApp message {i}",
                        timestamp=datetime.utcnow(),
                        attachments=[],
                        metadata={"type": "text"},
                    )
                )

            return thread
        except Exception as e:
            log.error("fetch_thread_history_failed", error=str(e))
            raise ValueError(f"Could not fetch thread history: {e}")

    def _normalize_phone(self, phone_number: str) -> str:
        """Normalize phone number to E.164 format.

        Args:
            phone_number: Raw phone number.

        Returns:
            str: Normalized phone in E.164 format.
        """
        # Remove non-digits
        digits = "".join(c for c in phone_number if c.isdigit())
        # Ensure starts with +
        if not phone_number.startswith("+"):
            digits = "+" + digits[-12:] if len(digits) >= 10 else "+" + digits
        else:
            digits = "+" + digits
        return digits

    def _is_in_window(self, phone_number: str) -> bool:
        """Check if phone number is in 24h messaging window.

        Args:
            phone_number: Phone number.

        Returns:
            bool: True if in window.
        """
        window = self.windows.get(phone_number)
        if not window:
            return False
        return window.is_within_window()

    def get_24h_window_info(self, phone_number: str) -> dict[str, Any]:
        """Get 24h window information for phone number.

        Args:
            phone_number: Phone number.

        Returns:
            Dict[str, Any]: Window info.
        """
        window = self.windows.get(phone_number)
        if not window:
            return {"in_window": False, "time_remaining": "expired"}

        time_remaining = window.calculate_time_remaining()
        return {
            "in_window": window.is_within_window(),
            "time_remaining_seconds": int(time_remaining.total_seconds()),
            "requires_template": window.requires_template(),
            "last_customer_message": window.last_customer_message_timestamp.isoformat(),
        }
