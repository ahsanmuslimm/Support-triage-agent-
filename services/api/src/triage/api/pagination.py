"""Cursor-based pagination and ETag support (S10.1)."""

import base64
import hashlib
import json
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorPaginationParams(BaseModel):
    """Cursor pagination parameters."""

    cursor: str | None = Field(None, description="Opaque cursor token")
    limit: int = Field(100, ge=1, le=100, description="Max results (1-100)")


class CursorPaginationResponse(BaseModel, Generic[T]):
    """Cursor pagination response."""

    items: list[T]
    next_cursor: str | None = Field(None, description="Cursor for next page")
    has_more: bool = Field(False, description="Whether more results available")


class CursorCodec:
    """Encode/decode cursor tokens."""

    @staticmethod
    def encode(item_id: str, created_at: datetime) -> str:
        """Encode cursor from item ID and creation timestamp.

        Args:
            item_id: Item ID (e.g., conversation_id)
            created_at: Item creation timestamp

        Returns:
            Base64-encoded cursor
        """
        # Format: "{item_id},{created_at_isoformat}"
        cursor_data = f"{item_id},{created_at.isoformat()}"
        cursor_bytes = cursor_data.encode("utf-8")
        return base64.b64encode(cursor_bytes).decode("utf-8")

    @staticmethod
    def decode(cursor: str) -> tuple[str, datetime]:
        """Decode cursor token.

        Args:
            cursor: Base64-encoded cursor

        Returns:
            (item_id, created_at) tuple

        Raises:
            ValueError: If cursor invalid
        """
        try:
            cursor_bytes = base64.b64decode(cursor.encode("utf-8"))
            cursor_data = cursor_bytes.decode("utf-8")
            item_id, created_at_iso = cursor_data.split(",", 1)
            created_at = datetime.fromisoformat(created_at_iso)
            return item_id, created_at
        except (ValueError, IndexError, TypeError) as e:
            raise ValueError(f"Invalid cursor: {e}")


class ETagManager:
    """Generate and validate ETags for resource versioning."""

    @staticmethod
    def generate(data: Any) -> str:
        """Generate ETag for data.

        Args:
            data: Data to tag (dict or JSON-serializable)

        Returns:
            ETag string
        """
        # Convert to JSON for consistent hashing
        if isinstance(data, dict):
            json_data = json.dumps(data, sort_keys=True, separators=(",", ":"))
        else:
            json_data = json.dumps(data, sort_keys=True)

        # SHA-256 hash
        hash_obj = hashlib.sha256(json_data.encode("utf-8"))
        return f'"{hash_obj.hexdigest()}"'

    @staticmethod
    def validate(etag: str, data: Any) -> bool:
        """Validate ETag matches data.

        Args:
            etag: ETag to validate
            data: Data to check

        Returns:
            True if ETag matches
        """
        expected_etag = ETagManager.generate(data)
        # Remove quotes for comparison
        etag_clean = etag.strip('"') if etag else ""
        expected_clean = expected_etag.strip('"')
        return etag_clean == expected_clean


class IdempotencyManager:
    """Manage idempotency for POST operations."""

    def __init__(self):
        # In production, use database with 24h retention
        self._store: dict[str, dict[str, Any]] = {}

    def record_request(
        self,
        idempotency_key: str,
        tenant_id: str,
        response_data: dict[str, Any],
    ) -> None:
        """Record request for idempotency.

        Args:
            idempotency_key: Client-provided UUID
            tenant_id: Tenant ID
            response_data: Response to return on duplicate
        """
        self._store[f"{tenant_id}:{idempotency_key}"] = {
            "response": response_data,
            "timestamp": datetime.utcnow(),
        }

    def get_cached_response(self, idempotency_key: str, tenant_id: str) -> dict[str, Any] | None:
        """Get cached response if exists.

        Args:
            idempotency_key: Client-provided UUID
            tenant_id: Tenant ID

        Returns:
            Cached response or None
        """
        key = f"{tenant_id}:{idempotency_key}"
        if key in self._store:
            entry = self._store[key]
            # Check if within 24h window
            age = datetime.utcnow() - entry["timestamp"]
            if age.total_seconds() <= 86400:  # 24 hours
                return entry["response"]
            else:
                # Expired, remove
                del self._store[key]
        return None

    def cleanup_expired(self):
        """Remove entries older than 24h."""
        now = datetime.utcnow()
        to_delete = []
        for key, entry in self._store.items():
            age = now - entry["timestamp"]
            if age.total_seconds() > 86400:
                to_delete.append(key)
        for key in to_delete:
            del self._store[key]
