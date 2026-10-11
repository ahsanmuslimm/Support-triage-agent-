"""Unit tests for Sprint 7 approval service.

Tests cover:
- Approval request creation
- Decision workflow
- 4h expiry and auto-escalation
- Slack integration
- Audit trail
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.api.src.triage.approval.approval_service import (
    ApprovalService,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalPriority,
)


@pytest.fixture
def approval_service():
    """Create approval service."""
    db_session = MagicMock()
    slack_client = AsyncMock()
    return ApprovalService(db_session, slack_client)


class TestApprovalRequestCreation:
    """Test approval request creation."""

    @pytest.mark.asyncio
    async def test_create_approval_request(self, approval_service):
        """Test creating an approval request."""
        result = await approval_service.create_request(
            action_id="act-1",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-1", "amount": 10000},
            context={"customer_tier": "standard"},
            priority=ApprovalPriority.MEDIUM,
        )

        assert result["id"] is not None
        assert result["action_type"] == "refund"
        assert result["status"] == ApprovalStatus.PENDING.value
        assert result["priority"] == ApprovalPriority.MEDIUM.value

    @pytest.mark.asyncio
    async def test_request_has_4h_expiry(self, approval_service):
        """Test that requests expire in 4 hours."""
        result = await approval_service.create_request(
            action_id="act-2",
            tenant_id="tenant-1",
            action_type="cancel_order",
            arguments={"order_id": "ord-2"},
            context={},
        )

        # Parse expiry time
        from dateutil.parser import parse as parse_iso
        created = parse_iso(result["created_at"])
        expires = parse_iso(result["expires_at"])
        
        delta = (expires - created).total_seconds()
        # Should be approximately 4 hours (14400 seconds), allow 1 second tolerance
        assert 14399 <= delta <= 14401

    @pytest.mark.asyncio
    async def test_slack_notification_sent(self, approval_service):
        """Test that Slack notification is sent."""
        await approval_service.create_request(
            action_id="act-3",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-3", "amount": 25000},
            context={},
        )

        # Verify Slack was called
        approval_service.slack_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_trail_recorded(self, approval_service):
        """Test that audit trail is recorded."""
        result = await approval_service.create_request(
            action_id="act-4",
            tenant_id="tenant-1",
            action_type="plan_change",
            arguments={"new_plan": "pro"},
            context={},
        )

        # Get the internal request
        request_id = result["id"]
        request = approval_service.pending_requests[request_id]
        
        assert len(request.audit_trail) > 0
        assert request.audit_trail[0]["event"] == "created"


class TestApprovalDecision:
    """Test approval decision workflow."""

    @pytest.mark.asyncio
    async def test_approve_request(self, approval_service):
        """Test approving a request."""
        # Create request
        request = await approval_service.create_request(
            action_id="act-5",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-5", "amount": 50000},
            context={},
        )
        request_id = request["id"]

        # Approve it
        decision = await approval_service.decide(
            request_id=request_id,
            approved=True,
            actor_id="user-admin",
            reason="Looks good",
        )

        assert decision["status"] == ApprovalStatus.APPROVED.value
        assert decision["decision"] is True
        assert decision["decided_by"] == "user-admin"

    @pytest.mark.asyncio
    async def test_reject_request(self, approval_service):
        """Test rejecting a request."""
        request = await approval_service.create_request(
            action_id="act-6",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-6", "amount": 100000},
            context={},
        )
        request_id = request["id"]

        decision = await approval_service.decide(
            request_id=request_id,
            approved=False,
            actor_id="user-reviewer",
            reason="Amount too high",
        )

        assert decision["status"] == ApprovalStatus.REJECTED.value
        assert decision["decision"] is False

    @pytest.mark.asyncio
    async def test_cannot_decide_twice(self, approval_service):
        """Test that a request cannot be decided twice."""
        request = await approval_service.create_request(
            action_id="act-7",
            tenant_id="tenant-1",
            action_type="cancel_order",
            arguments={"order_id": "ord-7"},
            context={},
        )
        request_id = request["id"]

        # First decision
        await approval_service.decide(
            request_id=request_id,
            approved=True,
            actor_id="user-1",
        )

        # Second decision should fail
        with pytest.raises(ValueError):
            await approval_service.decide(
                request_id=request_id,
                approved=False,
                actor_id="user-2",
            )

    @pytest.mark.asyncio
    async def test_audit_trail_updated_on_decision(self, approval_service):
        """Test audit trail is updated when decision is made."""
        request = await approval_service.create_request(
            action_id="act-8",
            tenant_id="tenant-1",
            action_type="password_reset",
            arguments={"email": "user@example.com"},
            context={},
        )
        request_id = request["id"]

        await approval_service.decide(
            request_id=request_id,
            approved=True,
            actor_id="user-admin",
            reason="Verified",
        )

        internal_request = approval_service.pending_requests[request_id]
        assert len(internal_request.audit_trail) >= 2
        assert internal_request.audit_trail[-1]["event"] == "decided"


class TestWaitForDecision:
    """Test waiting for approval decision."""

    @pytest.mark.asyncio
    async def test_wait_for_approval_completes(self, approval_service):
        """Test waiting for approval completes when decision is made."""
        request = await approval_service.create_request(
            action_id="act-9",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-9", "amount": 10000},
            context={},
        )
        request_id = request["id"]

        # Start waiting in background
        async def wait():
            return await approval_service.wait_for_decision(
                request_id, timeout_seconds=10
            )

        wait_task = asyncio.create_task(wait())
        
        # Give it time to start polling
        await asyncio.sleep(0.1)

        # Make decision
        await approval_service.decide(
            request_id=request_id,
            approved=True,
            actor_id="user-1",
        )

        # Wait should complete
        result = await asyncio.wait_for(wait_task, timeout=5)
        assert result["approved"] is True
        assert result["actor_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_wait_timeout_on_expiry(self, approval_service):
        """Test that wait returns False when request expires."""
        # Create request with short expiry for testing
        expires_at = datetime.utcnow() + timedelta(seconds=1)
        
        request_id = str(id(object()))
        request = ApprovalRequest(
            id=request_id,
            tenant_id="tenant-1",
            action_id="act-10",
            action_type="cancel_order",
            arguments={"order_id": "ord-10"},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.MEDIUM,
            expires_at=expires_at,
        )
        approval_service.pending_requests[request_id] = request

        # Wait for decision with longer timeout
        result = await approval_service.wait_for_decision(
            request_id, timeout_seconds=5
        )

        # Should return False on expiry
        assert result["approved"] is False
        assert result["actor_id"] == "system"


class TestAutoEscalation:
    """Test auto-escalation after 4h expiry."""

    @pytest.mark.asyncio
    async def test_expired_request_escalated(self, approval_service):
        """Test that expired request is auto-escalated."""
        # Create request with past expiry
        request_id = str(id(object()))
        request = ApprovalRequest(
            id=request_id,
            tenant_id="tenant-1",
            action_id="act-11",
            action_type="refund",
            arguments={"order_id": "ord-11", "amount": 50000},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.HIGH,
            expires_at=datetime.utcnow() - timedelta(seconds=1),  # Already expired
        )
        approval_service.pending_requests[request_id] = request

        # Wait should detect expiry
        result = await approval_service.wait_for_decision(
            request_id, timeout_seconds=2
        )

        # Check request was escalated
        assert request.status == ApprovalStatus.ESCALATED
        assert request.escalated_at is not None

    @pytest.mark.asyncio
    async def test_escalation_slack_notification(self, approval_service):
        """Test that escalation sends Slack notification."""
        request_id = str(id(object()))
        request = ApprovalRequest(
            id=request_id,
            tenant_id="tenant-1",
            action_id="act-12",
            action_type="password_reset",
            arguments={"email": "user@example.com"},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.CRITICAL,
            expires_at=datetime.utcnow() - timedelta(seconds=1),
        )
        approval_service.pending_requests[request_id] = request

        # Reset mock to track escalation call
        approval_service.slack_client.chat_postMessage.reset_mock()

        await approval_service.wait_for_decision(request_id, timeout_seconds=2)

        # Should send escalation message
        assert approval_service.slack_client.chat_postMessage.called


class TestSlackInteraction:
    """Test Slack interactive button handling."""

    @pytest.mark.asyncio
    async def test_slack_approve_button(self, approval_service):
        """Test handling Slack approve button."""
        request = await approval_service.create_request(
            action_id="act-13",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={"order_id": "ord-13", "amount": 20000},
            context={},
        )
        request_id = request["id"]

        # Simulate Slack interaction payload
        payload = {
            "actions": [{"action_id": f"approve_{request_id}"}],
            "user": {"id": "U123456"},
        }

        result = await approval_service.handle_slack_interaction(payload)

        assert "Approved" in result["text"]

        # Verify request is approved
        updated_request = approval_service.pending_requests[request_id]
        assert updated_request.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_slack_reject_button(self, approval_service):
        """Test handling Slack reject button."""
        request = await approval_service.create_request(
            action_id="act-14",
            tenant_id="tenant-1",
            action_type="cancel_order",
            arguments={"order_id": "ord-14"},
            context={},
        )
        request_id = request["id"]

        payload = {
            "actions": [{"action_id": f"reject_{request_id}"}],
            "user": {"id": "U789012"},
        }

        result = await approval_service.handle_slack_interaction(payload)

        assert "Rejected" in result["text"]

        updated_request = approval_service.pending_requests[request_id]
        assert updated_request.status == ApprovalStatus.REJECTED


class TestListAndGet:
    """Test request listing and retrieval."""

    @pytest.mark.asyncio
    async def test_get_request(self, approval_service):
        """Test getting a specific request."""
        request = await approval_service.create_request(
            action_id="act-15",
            tenant_id="tenant-1",
            action_type="address_change",
            arguments={"street": "123 Main"},
            context={},
        )
        request_id = request["id"]

        retrieved = await approval_service.get_request(request_id)

        assert retrieved is not None
        assert retrieved["id"] == request_id
        assert retrieved["action_type"] == "address_change"

    @pytest.mark.asyncio
    async def test_list_pending_requests(self, approval_service):
        """Test listing pending requests for a tenant."""
        # Create multiple requests
        await approval_service.create_request(
            action_id="act-16",
            tenant_id="tenant-1",
            action_type="refund",
            arguments={},
            context={},
        )
        await approval_service.create_request(
            action_id="act-17",
            tenant_id="tenant-1",
            action_type="cancel_order",
            arguments={},
            context={},
        )

        pending = await approval_service.list_pending("tenant-1")

        assert len(pending) >= 2
        assert all(r["status"] == ApprovalStatus.PENDING.value for r in pending)


class TestApprovalRequest:
    """Test ApprovalRequest data structure."""

    def test_request_is_expired(self):
        """Test expiry check."""
        request = ApprovalRequest(
            id="req-1",
            tenant_id="tenant-1",
            action_id="act-1",
            action_type="refund",
            arguments={},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.MEDIUM,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
        )

        assert request.is_expired() is True

    def test_request_not_expired(self):
        """Test non-expiry."""
        request = ApprovalRequest(
            id="req-2",
            tenant_id="tenant-1",
            action_id="act-2",
            action_type="cancel_order",
            arguments={},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.MEDIUM,
            expires_at=datetime.utcnow() + timedelta(hours=1),  # Not expired
        )

        assert request.is_expired() is False

    def test_request_to_dict(self):
        """Test request conversion to dict."""
        request = ApprovalRequest(
            id="req-3",
            tenant_id="tenant-1",
            action_id="act-3",
            action_type="password_reset",
            arguments={"email": "user@example.com"},
            context={},
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.LOW,
        )

        d = request.to_dict()
        assert d["id"] == "req-3"
        assert d["status"] == ApprovalStatus.PENDING.value
        assert d["priority"] == ApprovalPriority.LOW.value
