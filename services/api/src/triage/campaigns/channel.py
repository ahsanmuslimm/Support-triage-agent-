"""Channel selector for campaigns."""

import logging
from enum import Enum
from typing import ClassVar

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """Communication channels."""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class ChannelSelector:
    """Select optimal channel for customer."""

    CHANNEL_CAPACITY: ClassVar[dict[str, float]] = {
        "email": 0.15,
        "sms": 0.30,
        "push": 0.25,
    }

    def __init__(self):
        """Initialize selector."""
        self.sms_counts: dict = {}

    async def select_channel(
        self,
        customer_id: int,
        email_rate: float = 0.5,
        sms_rate: float = 0.5,
        push_rate: float = 0.5,
        sms_count_this_week: int = 0,
    ) -> str:
        """Select channel based on rates and caps."""
        SMS_FREQUENCY_CAP = 2

        if sms_rate >= 0.30 and sms_count_this_week < SMS_FREQUENCY_CAP:
            return Channel.SMS
        elif email_rate >= 0.15:
            return Channel.EMAIL
        elif push_rate >= 0.25:
            return Channel.PUSH
        else:
            return ""  # No channel available

    async def is_channel_available(
        self, customer_id: int, channel: str
    ) -> bool:
        """Check if channel is available for customer."""
        return channel in [Channel.EMAIL, Channel.SMS, Channel.PUSH]
