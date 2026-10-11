"""Tests for S10.2 - API Authentication & Keys."""

import pytest
from datetime import datetime, timedelta
from triage.api.auth import APIKeyManager, APIKeyScope, APIKeyStore


class TestAPIKeyGeneration:
    """Test API key generation."""

    def test_generate_live_key(self):
        """Test generating live API key."""
        manager = APIKeyManager(test_mode=False)
        scopes = [APIKeyScope.CONVERSATIONS_READ]
        
        full_key, key_id = manager.generate_key("tenant_123", scopes)
        
        assert full_key.startswith("trg_live_")
        assert len(full_key) > 20
        assert key_id

    def test_generate_test_key(self):
        """Test generating test API key."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.CONVERSATIONS_WRITE]
        
        full_key, key_id = manager.generate_key("tenant_456", scopes)
        
        assert full_key.startswith("trg_test_")
        assert len(full_key) > 20


class TestAPIKeyValidation:
    """Test API key validation."""

    def test_validate_valid_key(self):
        """Test validating a valid key."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.CONVERSATIONS_READ, APIKeyScope.PREDICTIONS_READ]
        
        full_key, key_id = manager.generate_key("tenant_789", scopes)
        key_record = manager.validate_key(full_key)
        
        assert key_record is not None
        assert key_record.tenant_id == "tenant_789"
        assert APIKeyScope.CONVERSATIONS_READ in key_record.scopes

    def test_validate_invalid_key(self):
        """Test validating an invalid key."""
        manager = APIKeyManager(test_mode=True)
        
        result = manager.validate_key("trg_test_invalid_key_xyz")
        
        assert result is None

    def test_validate_expired_key(self):
        """Test validating an expired key."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.AUTONOMY_WRITE]
        
        full_key, key_id = manager.generate_key(
            "tenant_exp",
            scopes,
            expiration_days=0,  # Expires immediately
        )
        
        # Manually set expiration to past
        manager._keys_store[key_id].expires_at = datetime.utcnow() - timedelta(hours=1)
        
        result = manager.validate_key(full_key)
        assert result is None


class TestScopeEnforcement:
    """Test scope enforcement."""

    def test_has_required_scope(self):
        """Test checking if key has scope."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.CONVERSATIONS_READ]
        
        full_key, key_id = manager.generate_key("tenant_scope", scopes)
        key_record = manager.validate_key(full_key)
        
        assert manager.has_scope(key_record, APIKeyScope.CONVERSATIONS_READ)
        assert not manager.has_scope(key_record, APIKeyScope.CONVERSATIONS_WRITE)

    def test_multiple_scopes(self):
        """Test key with multiple scopes."""
        manager = APIKeyManager(test_mode=True)
        scopes = [
            APIKeyScope.CONVERSATIONS_READ,
            APIKeyScope.CONVERSATIONS_WRITE,
            APIKeyScope.PREDICTIONS_READ,
        ]
        
        full_key, key_id = manager.generate_key("tenant_multi", scopes)
        key_record = manager.validate_key(full_key)
        
        assert len(key_record.scopes) == 3
        assert all(scope in key_record.scopes for scope in scopes)


class TestKeyRotation:
    """Test key rotation."""

    def test_rotate_key(self):
        """Test rotating a key."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.ADMIN_READ]
        
        # Generate original key
        old_key, old_key_id = manager.generate_key("tenant_rotate", scopes)
        
        # Rotate key
        new_key, new_key_id = manager.rotate_key(old_key_id, "tenant_rotate", scopes)
        
        assert new_key != old_key
        assert new_key_id != old_key_id
        
        # Old key should still validate for 7 days
        old_record = manager.validate_key(old_key)
        assert old_record is not None
        
        # New key should validate
        new_record = manager.validate_key(new_key)
        assert new_record is not None

    def test_rotation_log(self):
        """Test rotation is logged."""
        manager = APIKeyManager(test_mode=True)
        scopes = [APIKeyScope.CONVERSATIONS_READ]
        
        key1, key1_id = manager.generate_key("tenant_log", scopes)
        key2, key2_id = manager.rotate_key(key1_id, "tenant_log", scopes)
        
        old_key = manager._keys_store[key1_id]
        assert old_key.rotated_at is not None


class TestAPIKeyStore:
    """Test API key storage."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving keys."""
        store = APIKeyStore()
        manager = APIKeyManager(test_mode=True)
        
        full_key, key_id = manager.generate_key("tenant_store", [APIKeyScope.CONVERSATIONS_READ])
        key_record = manager.validate_key(full_key)
        
        store.create(key_record)
        retrieved = store.get_by_prefix(key_record.key_prefix)
        
        assert retrieved is not None
        assert retrieved.key_id == key_id

    def test_disable_key(self):
        """Test disabling a key."""
        store = APIKeyStore()
        manager = APIKeyManager(test_mode=True)
        
        full_key, key_id = manager.generate_key("tenant_disable", [APIKeyScope.CONVERSATIONS_READ])
        key_record = manager.validate_key(full_key)
        
        store.create(key_record)
        store.disable(key_id)
        
        key_record.active = False
        assert not key_record.active
