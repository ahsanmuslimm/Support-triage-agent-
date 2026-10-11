"""API authentication and authorization (S10.2)."""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Set
from enum import Enum
from dataclasses import dataclass, asdict
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash
import json


class APIKeyScope(str, Enum):
    """API key scopes for fine-grained access control."""

    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_WRITE = "conversations:write"
    PREDICTIONS_READ = "predictions:read"
    AUTONOMY_WRITE = "autonomy:write"
    ADMIN_READ = "admin:read"


@dataclass
class APIKey:
    """API key record."""

    key_id: str
    key_prefix: str  # trg_live_abc... or trg_test_xyz...
    key_hash: str  # Argon2id hash
    scopes: List[APIKeyScope]
    tenant_id: str
    active: bool = True
    created_at: datetime = None
    rotated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class APIKeyManager:
    """Manage API key generation, validation, and rotation."""

    def __init__(self, test_mode: bool = False):
        self.hasher = PasswordHasher()
        self.test_mode = test_mode
        self.environment = "test" if test_mode else "live"
        # In production, these would be database sessions
        self._keys_store: dict = {}

    def generate_key(
        self,
        tenant_id: str,
        scopes: List[APIKeyScope],
        expiration_days: Optional[int] = None,
    ) -> tuple[str, str]:
        """Generate a new API key.

        Args:
            tenant_id: Tenant ID
            scopes: List of scopes
            expiration_days: Days until expiration (optional)

        Returns:
            (full_key, key_id) tuple
        """
        # Generate 32-byte random value
        random_bytes = secrets.token_bytes(32)
        full_key = f"trg_{self.environment}_{secrets.token_urlsafe(32)}"

        # Compute prefix (first 16 chars after trg_live_ or trg_test_)
        prefix = full_key[:20]

        # Argon2id hash of full key
        key_hash = self.hasher.hash(full_key)

        # Generate key ID
        key_id = secrets.token_hex(12)

        # Create expires_at if needed
        expires_at = None
        if expiration_days:
            expires_at = datetime.utcnow() + timedelta(days=expiration_days)

        # Store key record
        key_record = APIKey(
            key_id=key_id,
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=scopes,
            tenant_id=tenant_id,
            expires_at=expires_at,
        )
        self._keys_store[key_id] = key_record

        return full_key, key_id

    def validate_key(self, full_key: str) -> Optional[APIKey]:
        """Validate an API key.

        Args:
            full_key: Full API key string

        Returns:
            APIKey record if valid, None otherwise
        """
        # Extract prefix
        prefix = full_key[:20]

        # Find key by prefix
        for key_id, key_record in self._keys_store.items():
            if key_record.key_prefix == prefix:
                # Check if active
                if not key_record.active:
                    return None

                # Check if expired
                if key_record.expires_at and datetime.utcnow() > key_record.expires_at:
                    return None

                # Verify hash
                try:
                    self.hasher.verify(key_record.key_hash, full_key)
                    return key_record
                except InvalidHash:
                    return None

        return None

    def rotate_key(self, old_key_id: str, tenant_id: str, scopes: List[APIKeyScope]) -> tuple[str, str]:
        """Rotate an API key (old key valid for 7 more days).

        Args:
            old_key_id: Key ID to rotate
            tenant_id: Tenant ID
            scopes: New scopes

        Returns:
            (new_full_key, new_key_id) tuple
        """
        if old_key_id in self._keys_store:
            old_key = self._keys_store[old_key_id]
            # Mark old key as rotated, keep valid for 7 more days
            old_key.rotated_at = datetime.utcnow()
            old_key.expires_at = datetime.utcnow() + timedelta(days=7)

        # Generate new key
        return self.generate_key(tenant_id, scopes)

    def has_scope(self, key: APIKey, required_scope: APIKeyScope) -> bool:
        """Check if key has required scope.

        Args:
            key: API key record
            required_scope: Required scope

        Returns:
            True if scope present
        """
        return required_scope in key.scopes


class APIKeyStore:
    """In-memory store for API keys. Replace with database in production."""

    def __init__(self):
        self.keys: dict[str, APIKey] = {}
        self.rotation_log: list = []

    def create(self, key: APIKey):
        """Store API key."""
        self.keys[key.key_id] = key

    def get_by_prefix(self, prefix: str) -> Optional[APIKey]:
        """Get key by prefix."""
        for key in self.keys.values():
            if key.key_prefix == prefix:
                return key
        return None

    def disable(self, key_id: str):
        """Disable key."""
        if key_id in self.keys:
            self.keys[key_id].active = False

    def log_rotation(self, old_key_id: str, new_key_id: str):
        """Log key rotation."""
        self.rotation_log.append({
            "old_key_id": old_key_id,
            "new_key_id": new_key_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
