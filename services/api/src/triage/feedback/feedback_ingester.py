"""S3.8: Feedback Collection and Storage."""

import logging
import json
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class FeedbackIngester:
    """Ingest feedback events (thumbs up/down, manual tags, escalation resolved)."""

    def __init__(self, db_session=None, redis_client=None):
        self.db = db_session
        self.redis = redis_client

    async def ingest(
        self,
        tenant_id: int,
        conversation_id: int,
        feedback_type: str,  # 'thumbs_up', 'thumbs_down', 'manual_tag', 'escalation_resolved'
        feedback_value: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Ingest feedback event.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            feedback_type: Type of feedback
            feedback_value: Tag value or manual notes
            metadata: Additional context

        Returns:
            Success flag
        """
        try:
            now = datetime.utcnow()

            # Store in DB
            if self.db:
                await self.db.execute(
                    """
                    INSERT INTO feedback_events (
                        tenant_id, conversation_id, feedback_type,
                        feedback_value, metadata, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    tenant_id,
                    conversation_id,
                    feedback_type,
                    feedback_value,
                    json.dumps(metadata or {}),
                    now,
                )

            # Store in Redis Streams for real-time processing
            if self.redis:
                stream_key = f"feedback:{tenant_id}"
                await self.redis.xadd(
                    stream_key,
                    {
                        "conversation_id": conversation_id,
                        "feedback_type": feedback_type,
                        "feedback_value": feedback_value or "",
                        "created_at": now.isoformat(),
                    },
                )

            logger.info(
                f"Ingested feedback: tenant={tenant_id}, conversation={conversation_id}, type={feedback_type}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to ingest feedback: {e}")
            return False
