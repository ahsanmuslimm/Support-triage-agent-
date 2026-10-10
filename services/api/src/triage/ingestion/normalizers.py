"""Message normalizers for different channels."""

import html
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from abc import ABC, abstractmethod

from ..models.message import CanonicalMessage, ChannelType, SenderType


class MessageNormalizer(ABC):
    """Base class for channel-specific normalizers."""

    @abstractmethod
    def normalize(
        self,
        tenant_id: str,
        conversation_id: str,
        channel_id: str,
        payload: Dict[str, Any],
    ) -> CanonicalMessage:
        """Normalize channel-specific payload to CanonicalMessage."""
        pass

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text: strip, decode HTML entities, collapse whitespace."""
        # Decode HTML entities
        text = html.unescape(text)
        # Strip leading/trailing whitespace
        text = text.strip()
        # Collapse multiple whitespace to single space (preserve newlines)
        lines = text.split("\n")
        lines = [" ".join(line.split()) for line in lines]
        return "\n".join(lines)

    @staticmethod
    def _detect_language(text: str) -> str:
        """Detect language of text (stub: returns 'en' for now)."""
        # TODO: Use langdetect library
        return "en"


class EmailNormalizer(MessageNormalizer):
    """Normalize email messages (via Zendesk or direct)."""

    def normalize(
        self,
        tenant_id: str,
        conversation_id: str,
        channel_id: str,
        payload: Dict[str, Any],
    ) -> CanonicalMessage:
        """Normalize email payload."""
        body = self._normalize_text(payload.get("body", ""))
        subject = payload.get("subject", "").strip()
        sender_email = payload.get("from", "")
        provider_message_id = payload.get("message_id")  # RFC 2822 Message-ID
        in_reply_to = payload.get("in_reply_to")
        references = payload.get("references", [])

        # Determine parent message ID from email threading
        parent_message_id = None
        if in_reply_to:
            parent_message_id = in_reply_to
        elif references:
            parent_message_id = references[-1]

        return CanonicalMessage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_type=ChannelType.EMAIL,
            body=body,
            subject=subject,
            sender_id=payload.get("sender_id", "unknown"),
            sender_type=SenderType.CUSTOMER,
            sender_email=sender_email,
            sender_name=payload.get("sender_name", ""),
            provider_message_id=provider_message_id,
            parent_message_id=parent_message_id,
            thread_id=payload.get("thread_id"),
            provider_timestamp=payload.get("timestamp"),
            metadata={
                "language": self._detect_language(body),
                "headers": payload.get("headers", {}),
            },
        )


class WebChatNormalizer(MessageNormalizer):
    """Normalize web chat messages from widget."""

    def normalize(
        self,
        tenant_id: str,
        conversation_id: str,
        channel_id: str,
        payload: Dict[str, Any],
    ) -> CanonicalMessage:
        """Normalize web chat payload."""
        body = self._normalize_text(payload.get("body", ""))

        return CanonicalMessage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_type=ChannelType.WEB_CHAT,
            body=body,
            sender_id=payload.get("sender_id", "anonymous"),
            sender_type=SenderType.CUSTOMER,
            sender_name=payload.get("sender_name"),
            sender_email=payload.get("sender_email"),
            provider_message_id=payload.get("message_id"),
            metadata={
                "language": self._detect_language(body),
                "session_id": payload.get("session_id"),
            },
        )


class ZendeskNormalizer(MessageNormalizer):
    """Normalize Zendesk comment payloads from webhook."""

    def normalize(
        self,
        tenant_id: str,
        conversation_id: str,
        channel_id: str,
        payload: Dict[str, Any],
    ) -> CanonicalMessage:
        """Normalize Zendesk payload."""
        # Extract comment from webhook
        comment = payload.get("comment", {})
        body = self._normalize_text(comment.get("body", ""))
        author_id = str(comment.get("author_id", "unknown"))

        # Determine if comment is from customer or agent
        is_public = comment.get("public", True)
        author_type = payload.get("author_type", "customer")  # "customer" or "agent"
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
            provider_timestamp=comment.get("created_at"),
            metadata={
                "language": self._detect_language(body),
                "is_public": is_public,
                "ticket_id": payload.get("ticket_id"),
                "attachments": comment.get("attachments", []),
            },
        )


class NormalizerFactory:
    """Factory to select appropriate normalizer by channel type."""

    _normalizers = {
        ChannelType.EMAIL: EmailNormalizer(),
        ChannelType.WEB_CHAT: WebChatNormalizer(),
        ChannelType.ZENDESK: ZendeskNormalizer(),
    }

    @classmethod
    def get_normalizer(cls, channel_type: ChannelType) -> MessageNormalizer:
        """Get normalizer for channel type."""
        if channel_type not in cls._normalizers:
            raise ValueError(f"No normalizer for channel type: {channel_type}")
        return cls._normalizers[channel_type]

    @classmethod
    def normalize(
        cls,
        channel_type: ChannelType,
        tenant_id: str,
        conversation_id: str,
        channel_id: str,
        payload: Dict[str, Any],
    ) -> CanonicalMessage:
        """Normalize payload to CanonicalMessage."""
        normalizer = cls.get_normalizer(channel_type)
        return normalizer.normalize(tenant_id, conversation_id, channel_id, payload)
