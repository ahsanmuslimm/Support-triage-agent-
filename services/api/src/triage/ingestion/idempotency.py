"""Idempotency management for exactly-once semantics."""

import hashlib
from typing import Tuple, Optional


class IdempotencyManager:
    """Manages idempotent message ingestion."""

    @staticmethod
    def compute_body_hash(body: str) -> str:
        """Compute SHA256 hash of normalized message body."""
        normalized = body.strip().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def generate_key(
        tenant_id: str,
        provider_message_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        body_hash: Optional[str] = None,
    ) -> str:
        """Generate deterministic idempotency key.

        Priority:
        1. provider_message_id (Zendesk ticket ID, email Message-ID)
        2. sender_id + body_hash (fallback for generated messages)
        """
        if provider_message_id:
            return f"{tenant_id}#{provider_message_id}"

        if sender_id and body_hash:
            return f"{tenant_id}#{sender_id}#{body_hash}"

        raise ValueError(
            "Must provide either provider_message_id or (sender_id + body_hash)"
        )

    @staticmethod
    def is_duplicate(
        existing_message_id: Optional[str],
    ) -> bool:
        """Check if message is a duplicate based on idempotency key lookup."""
        return existing_message_id is not None
