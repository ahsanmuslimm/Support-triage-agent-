"""Tests for S10.5, S10.8, S10.9 - Quality Dashboard, Data Residency, Sandbox."""

import pytest
from datetime import datetime, timedelta
from triage.analytics.quality_dashboard import QualityDashboard, ROIReport
from triage.compliance.data_residency import (
    DataResidencyManager,
    Datacenter,
    DataResidencyError,
    RegionLockManager,
)
from triage.sandbox.sandbox_tenant import SandboxTenant, get_sandbox_tenant


class TestQualityDashboard:
    """Test AI Quality Dashboard."""

    def test_compute_quality_metrics(self):
        """Test computing quality metrics."""
        dashboard = QualityDashboard()
        
        intent_predictions = [
            {"predicted": True},
            {"predicted": True},
            {"predicted": False},
        ]
        entity_extractions = [
            {"precision": 0.9, "recall": 0.85},
            {"precision": 0.88, "recall": 0.90},
        ]
        escalations = [False, False, True]
        false_resolutions = [False, False, False]
        costs = [0.02, 0.03, 0.01]
        
        metrics = dashboard.compute_quality_metrics(
            intent_predictions,
            entity_extractions,
            escalations,
            false_resolutions,
            costs,
        )
        
        assert metrics.intent_top1_accuracy == pytest.approx(2/3, rel=0.01)
        assert metrics.escalation_rate == pytest.approx(1/3, rel=0.01)
        assert metrics.entity_f1_score > 0

    def test_record_metrics(self):
        """Test recording metrics."""
        dashboard = QualityDashboard()
        
        from triage.analytics.quality_dashboard import QualityMetrics
        
        metrics = QualityMetrics(
            intent_top1_accuracy=0.95,
            entity_f1_score=0.92,
            groundedness=0.88,
            escalation_rate=0.05,
            false_resolution_rate=0.02,
            cost_per_resolution=0.025,
        )
        
        dashboard.record_metrics("tenant_1", datetime.utcnow(), metrics)
        
        assert len(dashboard.metrics_history) == 1

    def test_compute_roi(self):
        """Test computing ROI."""
        dashboard = QualityDashboard()
        
        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()
        
        report = dashboard.compute_roi(
            period_start,
            period_end,
            total_cost=1000.0,
            deflection_count=50,  # 50 * $50 = $2500
            faster_resolution_count=100,  # 100 * $10 = $1000
        )
        
        assert report.total_cost == 1000.0
        assert report.total_value == 3500.0
        assert report.net_roi == 2500.0

    def test_export_pdf(self):
        """Test PDF export."""
        dashboard = QualityDashboard()
        
        report = ROIReport(
            period_start="2026-01-01",
            period_end="2026-01-31",
            total_cost=1500.0,
            deflection_count=60,
            faster_resolution_count=80,
            total_value=3800.0,
            net_roi=2300.0,
            payback_period_days=4.7,
        )
        
        pdf_bytes = dashboard.export_pdf(report)
        
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_trending_metrics(self):
        """Test getting trending metrics."""
        dashboard = QualityDashboard()
        
        # Record metrics over time
        from triage.analytics.quality_dashboard import QualityMetrics
        
        for day in range(3):
            metrics = QualityMetrics(
                intent_top1_accuracy=0.90 + (day * 0.01),
                entity_f1_score=0.88 + (day * 0.01),
                groundedness=0.85,
                escalation_rate=0.05,
                false_resolution_rate=0.02,
                cost_per_resolution=0.025,
            )
            dashboard.record_metrics("tenant_1", datetime.utcnow(), metrics)
        
        trending = dashboard.get_trending_metrics("tenant_1", days=30)
        
        assert "intent_top1_accuracy" in trending
        assert len(trending["intent_top1_accuracy"]) >= 3


class TestDataResidency:
    """Test EU data residency enforcement."""

    def test_set_tenant_datacenter(self):
        """Test setting tenant datacenter."""
        manager = DataResidencyManager(test_mode=True)
        
        config = manager.set_tenant_datacenter("tenant_1", Datacenter.EU)
        
        assert config.datacenter == Datacenter.EU
        assert config.tenant_id == "tenant_1"

    def test_get_tenant_datacenter(self):
        """Test getting tenant datacenter."""
        manager = DataResidencyManager(test_mode=True)
        
        manager.set_tenant_datacenter("tenant_2", Datacenter.US)
        dc = manager.get_tenant_datacenter("tenant_2")
        
        assert dc == Datacenter.US

    @pytest.mark.asyncio
    async def test_verify_write_location_eu_compliant(self):
        """Test verifying EU-compliant write."""
        manager = DataResidencyManager(test_mode=True)
        manager.set_tenant_datacenter("tenant_eu", Datacenter.EU)
        
        result = await manager.verify_write_location(
            "tenant_eu",
            "conversation",
            "eu-postgresql-1",
        )
        
        assert result

    @pytest.mark.asyncio
    async def test_verify_write_location_violation(self):
        """Test detecting residency violation."""
        manager = DataResidencyManager(test_mode=True)
        manager.set_tenant_datacenter("tenant_eu", Datacenter.EU)
        
        with pytest.raises(DataResidencyError):
            await manager.verify_write_location(
                "tenant_eu",
                "conversation",
                "us-s3-bucket",
            )

    @pytest.mark.asyncio
    async def test_verify_egress_endpoint(self):
        """Test verifying egress endpoint."""
        manager = DataResidencyManager(test_mode=True)
        manager.set_tenant_datacenter("tenant_eu", Datacenter.EU)
        
        # EU endpoint should be allowed
        result = await manager.verify_egress_endpoint(
            "tenant_eu",
            "https://api.eu-openai.com/v1/chat/completions",
        )
        assert result

    @pytest.mark.asyncio
    async def test_verify_egress_endpoint_violation(self):
        """Test detecting egress violation."""
        manager = DataResidencyManager(test_mode=True)
        manager.set_tenant_datacenter("tenant_eu", Datacenter.EU)
        
        with pytest.raises(DataResidencyError):
            await manager.verify_egress_endpoint(
                "tenant_eu",
                "https://api.openai.com/v1/chat/completions",
            )

    def test_get_audit_log(self):
        """Test getting audit log."""
        manager = DataResidencyManager(test_mode=True)
        
        # Manually add log entry
        from triage.compliance.data_residency import DataResidencyAuditLog
        
        manager.audit_log.append(DataResidencyAuditLog(
            timestamp=datetime.utcnow(),
            tenant_id="tenant_1",
            operation="write",
            resource_type="conversation",
            datacenter=Datacenter.EU,
            location="eu-postgres",
            status="success",
        ))
        
        log = manager.get_audit_log("tenant_1")
        assert len(log) == 1


class TestRegionLock:
    """Test LiteLLM region locking."""

    def test_get_region_endpoint(self):
        """Test getting region-specific endpoint."""
        lock = RegionLockManager()
        
        endpoint = lock.get_region_endpoint(Datacenter.EU, "openai")
        
        assert endpoint is not None
        assert "openai" in endpoint.lower()

    def test_validate_endpoint_region(self):
        """Test validating endpoint matches region."""
        lock = RegionLockManager()
        
        # EU tenant can use EU endpoint
        assert lock.validate_endpoint_region(Datacenter.EU, "https://api.eu-openai.com")


class TestSandboxTenant:
    """Test sandbox tenant."""

    def test_sandbox_initialization(self):
        """Test sandbox initialization."""
        sandbox = SandboxTenant()
        
        # Check that data is loaded and initial state is saved
        assert sandbox.initial_state is not None
        assert sandbox.verify_initialization()
        assert len(sandbox.conversations) == 5
        assert len(sandbox.messages) == 20
        assert len(sandbox.kb_entries) == 5

    def test_get_sample_conversations(self):
        """Test getting sample conversations."""
        sandbox = SandboxTenant()
        
        convs = sandbox.get_sample_conversations(limit=3)
        
        assert len(convs) == 3

    def test_get_sample_messages(self):
        """Test getting messages for conversation."""
        sandbox = SandboxTenant()
        
        messages = sandbox.get_sample_messages("conv_sandbox_001")
        
        assert len(messages) > 0

    def test_get_kb(self):
        """Test getting knowledge base."""
        sandbox = SandboxTenant()
        
        kb = sandbox.get_kb()
        
        assert len(kb) == 5

    @pytest.mark.asyncio
    async def test_dry_run_write(self):
        """Test dry-run write operation."""
        sandbox = SandboxTenant()
        
        result = await sandbox.dry_run_write("charge", "stripe", amount=100)
        
        assert result["success"]
        assert result["dry_run"]
        assert "stripe" in result["provider"]

    @pytest.mark.asyncio
    async def test_reset_to_initial_state(self):
        """Test resetting sandbox."""
        sandbox = SandboxTenant()
        
        # Modify data
        sandbox.conversations = []
        
        # Reset
        success = await sandbox.reset_to_initial_state()
        
        assert success
        assert len(sandbox.conversations) == 5

    def test_singleton_instance(self):
        """Test sandbox singleton."""
        sandbox1 = get_sandbox_tenant()
        sandbox2 = get_sandbox_tenant()
        
        assert sandbox1 is sandbox2
