"""Tests for S10.1 - Pagination, ETag, RFC 9457 Errors."""

import pytest
from datetime import datetime, timedelta
from triage.api.pagination import CursorCodec, ETagManager, IdempotencyManager
from triage.api.errors import (
    InvalidScopeError,
    InvalidAPIKeyError,
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    RateLimitError,
)


class TestCursorPagination:
    """Test cursor-based pagination."""

    def test_encode_cursor(self):
        """Test cursor encoding."""
        now = datetime.utcnow()
        cursor = CursorCodec.encode("item_123", now)
        
        assert isinstance(cursor, str)
        assert len(cursor) > 0

    def test_decode_cursor(self):
        """Test cursor decoding."""
        now = datetime.utcnow()
        original_id = "item_456"
        
        cursor = CursorCodec.encode(original_id, now)
        decoded_id, decoded_time = CursorCodec.decode(cursor)
        
        assert decoded_id == original_id
        assert abs((decoded_time - now).total_seconds()) < 1

    def test_decode_invalid_cursor(self):
        """Test decoding invalid cursor."""
        with pytest.raises(ValueError):
            CursorCodec.decode("invalid_base64_!!!!")

    def test_cursor_roundtrip(self):
        """Test cursor encode/decode roundtrip."""
        ids = ["conv_001", "conv_002", "msg_xyz"]
        now = datetime.utcnow()
        
        for item_id in ids:
            cursor = CursorCodec.encode(item_id, now)
            decoded_id, _ = CursorCodec.decode(cursor)
            assert decoded_id == item_id


class TestETag:
    """Test ETag generation and validation."""

    def test_generate_etag(self):
        """Test ETag generation."""
        data = {"id": "123", "name": "test"}
        etag = ETagManager.generate(data)
        
        assert etag.startswith('"')
        assert etag.endswith('"')
        assert len(etag) > 10

    def test_etag_consistent(self):
        """Test ETag is consistent for same data."""
        data = {"id": "456", "status": "open"}
        
        etag1 = ETagManager.generate(data)
        etag2 = ETagManager.generate(data)
        
        assert etag1 == etag2

    def test_etag_different_for_different_data(self):
        """Test ETag differs for different data."""
        data1 = {"id": "789", "status": "open"}
        data2 = {"id": "789", "status": "closed"}
        
        etag1 = ETagManager.generate(data1)
        etag2 = ETagManager.generate(data2)
        
        assert etag1 != etag2

    def test_validate_etag(self):
        """Test ETag validation."""
        data = {"id": "test", "value": 42}
        etag = ETagManager.generate(data)
        
        assert ETagManager.validate(etag, data)

    def test_validate_invalid_etag(self):
        """Test invalid ETag validation."""
        data = {"id": "test", "value": 42}
        wrong_data = {"id": "test", "value": 43}
        etag = ETagManager.generate(data)
        
        assert not ETagManager.validate(etag, wrong_data)


class TestIdempotency:
    """Test idempotency support."""

    def test_record_request(self):
        """Test recording idempotent request."""
        manager = IdempotencyManager()
        idempotency_key = "req_abc123"
        response = {"id": "msg_001", "status": "created"}
        
        manager.record_request(idempotency_key, "tenant_1", response)
        
        cached = manager.get_cached_response(idempotency_key, "tenant_1")
        assert cached == response

    def test_cached_response_not_found(self):
        """Test non-existent cache entry."""
        manager = IdempotencyManager()
        
        cached = manager.get_cached_response("req_nonexistent", "tenant_1")
        
        assert cached is None

    def test_idempotency_24h_window(self):
        """Test 24h retention window."""
        manager = IdempotencyManager()
        key = "req_24h"
        response = {"id": "123"}
        
        manager.record_request(key, "tenant_1", response)
        
        # Should retrieve within window
        cached = manager.get_cached_response(key, "tenant_1")
        assert cached is not None
        
        # Manually expire
        entry = manager._store[f"tenant_1:{key}"]
        entry["timestamp"] = datetime.utcnow() - timedelta(hours=25)
        
        # Should not retrieve after expiry
        cached = manager.get_cached_response(key, "tenant_1")
        assert cached is None

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        manager = IdempotencyManager()
        
        # Add old entry
        old_key = "req_old"
        manager._store[f"tenant_1:{old_key}"] = {
            "response": {"id": "old"},
            "timestamp": datetime.utcnow() - timedelta(hours=30),
        }
        
        # Add fresh entry
        new_key = "req_new"
        manager.record_request(new_key, "tenant_1", {"id": "new"})
        
        # Cleanup
        manager.cleanup_expired()
        
        # Old should be gone
        assert f"tenant_1:{old_key}" not in manager._store
        # New should remain
        assert f"tenant_1:{new_key}" in manager._store


class TestRFC9457Errors:
    """Test RFC 9457 error formatting."""

    def test_invalid_scope_error(self):
        """Test InvalidScopeError format."""
        error = InvalidScopeError("conversations:write", "/api/v1/conversations/123/messages")
        
        assert error.status_code == 403
        assert "conversations:write" in error.detail_text

    def test_invalid_api_key_error(self):
        """Test InvalidAPIKeyError format."""
        error = InvalidAPIKeyError("/api/v1/conversations")
        
        assert error.status_code == 401
        assert "invalid" in error.detail_text.lower()

    def test_conflict_error(self):
        """Test ConflictError format."""
        error = ConflictError("Duplicate idempotency key", "/api/v1/messages")
        
        assert error.status_code == 409
        assert "Duplicate" in error.detail_text

    def test_not_found_error(self):
        """Test NotFoundError format."""
        error = NotFoundError("Conversation", "conv_xyz")
        
        assert error.status_code == 404
        assert "conv_xyz" in error.detail_text

    def test_precondition_failed_error(self):
        """Test PreconditionFailedError format."""
        error = PreconditionFailedError("ETag mismatch")
        
        assert error.status_code == 412
        assert "ETag" in error.detail_text

    def test_rate_limit_error(self):
        """Test RateLimitError format."""
        reset_at = int((datetime.utcnow() + timedelta(minutes=1)).timestamp())
        error = RateLimitError(reset_at)
        
        assert error.status_code == 429
        assert "extensions" in dir(error)
