"""Zendesk webhook receiver with HMAC signature verification."""

import hmac
import hashlib
import json
from typing import Dict, Any, Optional
from ..models.message import CanonicalMessage


class ZendeskWebhookHandler:
    """Handles signed Zendesk webhook payloads."""

    def __init__(self, webhook_secret: Optional[str] = None):
        """Initialize handler.

        Args:
            webhook_secret: Zendesk webhook secret for HMAC verification
        """
        self.webhook_secret = webhook_secret

    def verify_signature(
        self,
        payload: str,
        signature_header: str,
    ) -> bool:
        """Verify HMAC-SHA256 signature of webhook payload.

        Args:
            payload: Raw request body as string
            signature_header: X-Zendesk-Webhook-Signature header value

        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            # Skip verification if no secret configured
            return True

        # Compute expected signature
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Compare (timing-safe)
        return hmac.compare_digest(expected_signature, signature_header)

    def parse_payload(
        self,
        raw_payload: str,
    ) -> Dict[str, Any]:
        """Parse JSON payload.

        Args:
            raw_payload: Raw JSON string

        Returns:
            Parsed payload dict
        """
        return json.loads(raw_payload)

    def extract_message(
        self,
        payload: Dict[str, Any],
        tenant_id: str,
        conversation_id: str,
        channel_id: str = "zendesk",
    ) -> Optional[CanonicalMessage]:
        """Extract CanonicalMessage from Zendesk webhook payload.

        Args:
            payload: Parsed webhook payload
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            channel_id: Channel ID

        Returns:
            CanonicalMessage or None if not a message event
        """
        event_type = payload.get("event_type")

        # Only process comment events
        if event_type != "ticket_comment":
            return None

        # Extract comment data
        comment = payload.get("comment", {})
        author_id = str(comment.get("author_id"))
        body = comment.get("body", "")

        if not body:
            return None

        # Determine sender type
        author_type = payload.get("author_type", "customer")
        from ..models.message import SenderType, ChannelType

        sender_type = (
            SenderType.AGENT if author_type == "agent" else SenderType.CUSTOMER
        )

        return CanonicalMessage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_type=ChannelType.ZENDESK,
            body=body,
            sender_id=author_id,
            sender_type=sender_type,
            sender_name=payload.get("author_name", ""),
            sender_email=payload.get("author_email", ""),
            provider_message_id=str(comment.get("id")),
            metadata={
                "ticket_id": payload.get("ticket_id"),
                "is_public": comment.get("public", True),
            },
        )

    async def write_to_zendesk(
        self,
        ticket_id: int,
        message: str,
        internal: bool = True,
    ) -> bool:
        """Write response back to Zendesk ticket (stub).

        Args:
            ticket_id: Zendesk ticket ID
            message: Message to post
            internal: True for internal note, False for public comment

        Returns:
            True if successful
        """
        # TODO: Implement Zendesk API call
        # POST https://zendesk.com/api/v2/tickets/{ticket_id}/comments
        print(f"Would write to Zendesk ticket {ticket_id}: {message}")
        return True
