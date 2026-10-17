"""Tests for S10.7 - DSAR & Right-to-Erasure."""

from datetime import datetime

import pytest
from triage.compliance.dsar import (
    DSARManager,
    DSARStatus,
)


class TestDSARManager:
    """Test DSAR request management."""

    @pytest.mark.asyncio
    async def test_request_export(self):
        """Test requesting data export."""
        manager = DSARManager(test_mode=True)

        request = await manager.request_export("tenant_1", "cust_123")

        assert request.request_type == "export"
        assert request.status == DSARStatus.PENDING
        assert request.customer_id == "cust_123"

    @pytest.mark.asyncio
    async def test_request_erasure(self):
        """Test requesting erasure."""
        manager = DSARManager(test_mode=True)

        request = await manager.request_erasure("tenant_1", "cust_456")

        assert request.request_type == "erasure"
        assert request.status == DSARStatus.PENDING

    @pytest.mark.asyncio
    async def test_validate_request(self):
        """Test validating request."""
        manager = DSARManager(test_mode=True)

        request = await manager.request_export("tenant_1", "cust_789")
        valid = await manager.validate_request(request.request_id)

        assert valid

    @pytest.mark.asyncio
    async def test_execute_export(self):
        """Test executing export."""
        manager = DSARManager(test_mode=True)

        # Add some data
        manager.conversations_db.append({
            "id": "conv_1",
            "customer_id": "cust_export",
            "tenant_id": "tenant_1",
            "content": "conversation data",
        })
        manager.messages_db.append({
            "id": "msg_1",
            "customer_id": "cust_export",
            "body": "message content",
        })

        request = await manager.request_export("tenant_1", "cust_export")
        export = await manager.execute_export(request.request_id)

        assert export is not None
        assert len(export.conversations) == 1
        assert len(export.messages) == 1
        assert request.status == DSARStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_erasure(self):
        """Test executing erasure."""
        manager = DSARManager(test_mode=True)

        # Add data
        manager.conversations_db.append({
            "id": "conv_erase",
            "customer_id": "cust_erase",
            "tenant_id": "tenant_1",
        })
        manager.messages_db.append({
            "id": "msg_erase",
            "customer_id": "cust_erase",
        })

        request = await manager.request_erasure("tenant_1", "cust_erase")
        success = await manager.execute_erasure(request.request_id)

        assert success
        assert request.status == DSARStatus.COMPLETED

        # Verify data is gone
        remaining = [c for c in manager.conversations_db if c["customer_id"] == "cust_erase"]
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_verify_erasure(self):
        """Test post-erasure verification."""
        manager = DSARManager(test_mode=True)

        # Add and then erase
        manager.conversations_db.append({
            "id": "conv_verify",
            "customer_id": "cust_verify",
        })

        verified = await manager._verify_erasure("cust_verify_nonexistent")
        assert verified

        verified = await manager._verify_erasure("cust_verify")
        assert not verified

    def test_get_request_status(self):
        """Test getting request status."""
        manager = DSARManager(test_mode=True)

        import asyncio
        request = asyncio.run(manager.request_export("tenant_1", "cust_status"))

        status_request = manager.get_request_status(request.request_id)

        assert status_request is not None
        assert status_request.status == DSARStatus.PENDING

    def test_get_erasure_log(self):
        """Test getting erasure log."""
        manager = DSARManager(test_mode=True)

        # Manually add log entry
        manager.erasure_log.append({
            "request_id": "req_123",
            "customer_id": "cust_log",
            "tenant_id": "tenant_1",
            "duration_seconds": 5.0,
            "completed_at": datetime.utcnow().isoformat(),
        })

        log = manager.get_erasure_log("tenant_1")

        assert len(log) == 1
        assert log[0]["customer_id"] == "cust_log"
