"""Message coalescing for conversation batching."""

import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from ..models.message import CanonicalMessage, ChannelType


class MessageCoalescer:
    """Groups related messages into conversations for batch processing.

    Uses debouncing to collect messages within a time window:
    - Email: 0s (immediate)
    - Web chat: 4s
    - Other: 2s

    Prevents duplicate triage runs on rapid message bursts.
    """

    # Debounce intervals per channel (in seconds)
    DEBOUNCE_INTERVALS = {
        ChannelType.EMAIL: 0,
        ChannelType.WEB_CHAT: 4,
        ChannelType.ZENDESK: 0,
        ChannelType.API: 2,
    }

    def __init__(self, redis_client=None):
        """Initialize coalescer.

        Args:
            redis_client: Redis client for distributed locking. If None, uses in-memory store.
        """
        self.redis = redis_client
        self._in_memory_store: Dict[str, Dict[str, Any]] = {}  # Demo mode

    def find_or_create_conversation(
        self,
        message: CanonicalMessage,
    ) -> str:
        """Find or create conversation for message.

        Implements debouncing and locking to prevent duplicate triage runs.

        Args:
            message: Canonical message

        Returns:
            Conversation ID
        """
        conversation_id = message.conversation_id
        coalesce_key = f"coalesce:{message.tenant_id}:{conversation_id}"
        lock_key = f"lock:{message.tenant_id}:{conversation_id}"

        # TODO: Implement Redis-based lock acquisition
        # For now, return conversation_id as-is
        return conversation_id

    def queue_message(
        self,
        message: CanonicalMessage,
    ) -> bool:
        """Queue message for coalescing.

        Returns:
            True if queued for debounce, False if should process immediately
        """
        debounce_interval = self.DEBOUNCE_INTERVALS.get(
            message.channel_type, 2
        )

        if debounce_interval == 0:
            return False  # Process immediately (email, Zendesk)

        return True  # Queue for debounce

    def get_debounce_interval(self, channel_type: ChannelType) -> int:
        """Get debounce interval for channel type (in seconds)."""
        return self.DEBOUNCE_INTERVALS.get(channel_type, 2)
