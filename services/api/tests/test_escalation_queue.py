"""Tests for escalation queue manager (S4.5)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from triage.escalation.queue_manager import EscalationQueueManager
from triage.escalation.models import EscalationJob, Priority


class TestEscalationQueueManager:
    """Test EscalationQueueManager."""

    @pytest.fixture
    def manager(self):
        """Create queue manager."""
        return EscalationQueueManager()

    @pytest.fixture
    def sample_job(self):
        """Create sample escalation job."""
        return EscalationJob(
            tenant_id=1,
            ticket_id="TICKET-001",
            priority=Priority.P1,
            deadline=datetime.utcnow() + timedelta(hours=1),
            status="pending",
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager.sla_grace_minutes == 5

    @pytest.mark.asyncio
    async def test_enqueue_job(self, manager, sample_job):
        """Test enqueueing a job."""
        result = await manager.enqueue(sample_job)
        assert result is True

    @pytest.mark.asyncio
    async def test_assign_to_agent(self, manager):
        """Test assigning job to agent."""
        result = await manager.assign_to_agent(1, "agent@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_resolve_job(self, manager):
        """Test resolving a job."""
        result = await manager.resolve_job(1, "Resolved successfully")
        assert result is True

    @pytest.mark.asyncio
    async def test_detect_sla_breaches(self, manager):
        """Test detecting SLA breaches."""
        breaches = await manager.detect_sla_breaches(1)
        assert isinstance(breaches, list)

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, manager):
        """Test getting queue statistics."""
        stats = await manager.get_queue_stats(1)
        assert "pending_count" in stats
        assert "assigned_count" in stats
        assert "overdue_count" in stats
        assert "sla_breach_pct" in stats
        assert "as_of" in stats

    @pytest.mark.asyncio
    async def test_audit_log_action(self, manager):
        """Test audit logging."""
        result = await manager._audit_log(
            tenant_id=1,
            escalation_id=1,
            action="enqueued",
            details={"ticket_id": "TICKET-001"},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_emit_alert_webhook(self, manager, sample_job):
        """Test emitting alert webhook."""
        result = await manager._emit_alert_webhook(sample_job)
        assert result is True

    @pytest.mark.asyncio
    async def test_sla_grace_period(self, manager):
        """Test SLA grace period for auto-escalation."""
        assert manager.sla_grace_minutes == 5

    @pytest.mark.asyncio
    async def test_enqueue_multiple_jobs(self, manager):
        """Test enqueueing multiple jobs."""
        jobs = []
        for i in range(3):
            job = EscalationJob(
                tenant_id=1,
                ticket_id=f"TICKET-{i}",
                priority=Priority.P1,
                deadline=datetime.utcnow() + timedelta(hours=1),
                status="pending",
                created_at=datetime.utcnow(),
            )
            result = await manager.enqueue(job)
            assert result is True
            jobs.append(job)

    @pytest.mark.asyncio
    async def test_job_status_transitions(self, manager):
        """Test job status transitions."""
        job = EscalationJob(
            tenant_id=1,
            ticket_id="TICKET-001",
            priority=Priority.P1,
            deadline=datetime.utcnow() + timedelta(hours=1),
            status="pending",
            created_at=datetime.utcnow(),
        )
        
        # Enqueue
        result = await manager.enqueue(job)
        assert result is True
        
        # Assign
        result = await manager.assign_to_agent(job.id or 0, "agent@example.com")
        assert result is True
        
        # Resolve
        result = await manager.resolve_job(job.id or 0, "Done")
        assert result is True
