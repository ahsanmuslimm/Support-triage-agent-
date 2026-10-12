"""S6.4: Priority queues for routing messages by SLA (chat vs email)."""
import json
from datetime import datetime
from enum import IntEnum
from typing import Any

import structlog

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

log = structlog.get_logger(__name__)


class Channel(IntEnum):
    """Channel priority (lower number = higher priority).

    Design (S6.4):
    Channels mapped to SLA requirements and worker concurrency.
    """

    CHAT = 1  # Urgent (1-min SLA)
    WEB = 2  # High (2-min SLA)
    EMAIL = 10  # Low (8-hour SLA)
    VOICE = 0  # Reserved for future


class PriorityQueue:
    """Redis-backed priority queue for routing messages to worker lanes.

    Design (S6.4):
    - Two Application-Level Queues:
      * Chat Lane: 10 workers, SLA 1 min (urgent)
      * Email Lane: 3 workers, SLA 8 hours (batch)
    - Each lane is FIFO queue backed by Redis sorted sets
    - Score = priority (channel) + arrival time (for within-priority ordering)
    - Prevents starvation: chat never waits for email

    Integration:
    - Enqueue: when message arrives (after classification)
    - Dequeue: by worker pools (one per lane)
    - Routing: application logic selects lane based on channel + SLA
    """

    def __init__(self, redis_client: Any):
        if redis_client is None:
            raise ValueError("Redis client required for PriorityQueue")

        self.redis = redis_client
        self.chat_queue_key = "queue:chat"
        self.email_queue_key = "queue:email"
        self.dlq_queue_key = "queue:dlq"

    async def enqueue_message(
        self,
        message_id: str,
        tenant_id: str,
        channel: str,
        payload: dict[str, Any],
    ) -> str:
        """Enqueue message to appropriate lane.

        Args:
            message_id: Message ID
            tenant_id: Tenant context
            channel: "chat", "email", "web"
            payload: Message data

        Returns:
            Queue name message was sent to
        """
        try:
            # Determine priority
            priority_channel = Channel[channel.upper()]

            # Select queue
            if priority_channel in (Channel.CHAT, Channel.WEB):
                queue_key = self.chat_queue_key
                workers = 10
            elif priority_channel == Channel.EMAIL:
                queue_key = self.email_queue_key
                workers = 3
            else:
                queue_key = self.dlq_queue_key
                workers = 1

            # Score = priority (lower = higher priority) + arrival time
            # This ensures: within same priority, FIFO ordering
            score = float(priority_channel) + (datetime.utcnow().timestamp() / 1e6)

            # Wrap message
            item = {
                "message_id": message_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "payload": payload,
                "enqueued_at": datetime.utcnow().isoformat(),
            }

            # Add to sorted set (score = priority + time)
            await self.redis.zadd(
                queue_key,
                {json.dumps(item): score},
            )

            log.info(
                "message_enqueued",
                message_id=message_id,
                channel=channel,
                queue=queue_key,
                workers=workers,
            )

            return queue_key

        except Exception as e:
            log.exception("enqueue_message_failed", error=str(e))
            raise

    async def dequeue_message(
        self,
        channel: str,
        batch_size: int = 1,
    ) -> list[dict[str, Any]]:
        """Dequeue message(s) from lane.

        Args:
            channel: "chat" or "email"
            batch_size: Number of messages to dequeue

        Returns:
            List of messages (empty if queue empty)
        """
        try:
            queue_key = self.chat_queue_key if channel == "chat" else self.email_queue_key

            # Get lowest-scored items (highest priority)
            items = await self.redis.zrange(
                queue_key, 0, batch_size - 1, withscores=False
            )

            # Remove from queue
            if items:
                await self.redis.zrem(queue_key, *items)

            # Parse and return
            messages = [json.loads(item) for item in items]

            log.info(
                "message_dequeued",
                channel=channel,
                count=len(messages),
            )

            return messages

        except Exception as e:
            log.exception("dequeue_message_failed", error=str(e))
            raise

    async def get_queue_depth(self, channel: str) -> int:
        """Get number of messages in queue.

        Args:
            channel: "chat" or "email"

        Returns:
            Number of messages waiting in queue
        """
        try:
            queue_key = self.chat_queue_key if channel == "chat" else self.email_queue_key
            depth = await self.redis.zcard(queue_key)
            return depth
        except Exception as e:
            log.exception("get_queue_depth_failed", error=str(e))
            return 0

    async def get_queue_stats(self) -> dict[str, Any]:
        """Get statistics for all queues.

        Returns:
            Dictionary with queue depths and SLA info
        """
        try:
            chat_depth = await self.get_queue_depth("chat")
            email_depth = await self.get_queue_depth("email")

            return {
                "chat": {
                    "depth": chat_depth,
                    "workers": 10,
                    "sla_mins": 1,
                },
                "email": {
                    "depth": email_depth,
                    "workers": 3,
                    "sla_hours": 8,
                },
            }
        except Exception as e:
            log.exception("get_queue_stats_failed", error=str(e))
            return {}
