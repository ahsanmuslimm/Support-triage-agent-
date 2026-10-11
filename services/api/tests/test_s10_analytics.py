"""Tests for S10.4 - ClickHouse Analytics."""

import pytest
from datetime import datetime, timedelta
from triage.analytics.clickhouse import (
    ConversationEvent,
    LLMInvocation,
    ClickhouseAnalytics,
)


class TestClickhouseAnalytics:
    """Test ClickHouse analytics engine."""

    @pytest.mark.asyncio
    async def test_ingest_conversation_event(self):
        """Test ingesting conversation event."""
        analytics = ClickhouseAnalytics(test_mode=True)
        
        event = ConversationEvent(
            conversation_id="conv_123",
            tenant_id="tenant_1",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            status="resolved",
            intent_primary="billing",
            intent_secondary=None,
            is_auto_resolved=True,
            escalation_triggered=False,
            metadata={},
        )
        
        await analytics.ingest_conversation_event(event)
        
        assert len(analytics.conversation_events) == 1

    @pytest.mark.asyncio
    async def test_ingest_llm_invocation(self):
        """Test ingesting LLM invocation."""
        analytics = ClickhouseAnalytics(test_mode=True)
        
        invocation = LLMInvocation(
            invocation_id="inv_456",
            tenant_id="tenant_1",
            conversation_id="conv_123",
            model="gpt-4",
            latency_ms=250.5,
            cost_usd=0.03,
            tokens_prompt=100,
            tokens_completion=50,
            timestamp=datetime.utcnow(),
        )
        
        await analytics.ingest_llm_invocation(invocation)
        
        assert len(analytics.llm_invocations) == 1

    @pytest.mark.asyncio
    async def test_compute_kpis(self):
        """Test computing KPIs."""
        analytics = ClickhouseAnalytics(test_mode=True)
        
        now = datetime.utcnow()
        
        # Add 10 events
        for i in range(10):
            event = ConversationEvent(
                conversation_id=f"conv_{i}",
                tenant_id="tenant_1",
                created_at=now,
                updated_at=now + timedelta(hours=1),
                status="resolved",
                intent_primary="billing" if i % 2 == 0 else "technical",
                intent_secondary=None,
                is_auto_resolved=i < 7,  # 7 auto-resolved
                escalation_triggered=i >= 8,  # 2 escalated
                metadata={},
            )
            await analytics.ingest_conversation_event(event)
        
        # Compute KPIs
        kpi = analytics.compute_kpis("tenant_1", now, now + timedelta(days=1))
        
        assert kpi is not None
        assert kpi.total_conversations == 10
        assert kpi.total_auto_resolved == 7
        assert kpi.total_escalations == 2
        assert kpi.escalation_rate == 0.2
        assert kpi.self_service_rate == 0.7

    def test_query_kpis(self):
        """Test querying KPIs across date range."""
        analytics = ClickhouseAnalytics(test_mode=True)
        
        # Add events for 3 days
        for day in range(3):
            date = datetime.utcnow() + timedelta(days=day)
            for i in range(5):
                event = ConversationEvent(
                    conversation_id=f"conv_{day}_{i}",
                    tenant_id="tenant_1",
                    created_at=date,
                    updated_at=date,
                    status="resolved",
                    intent_primary="billing",
                    intent_secondary=None,
                    is_auto_resolved=True,
                    escalation_triggered=False,
                    metadata={},
                )
                # Synchronous call for test
                import asyncio
                asyncio.run(analytics.ingest_conversation_event(event))
        
        start_date = datetime.utcnow().date().isoformat()
        end_date = (datetime.utcnow() + timedelta(days=2)).date().isoformat()
        
        kpis = analytics.query_kpis("tenant_1", start_date, end_date)
        
        assert len(kpis) > 0

    def test_get_table_schema(self):
        """Test retrieving table schema."""
        analytics = ClickhouseAnalytics()
        
        schema = analytics.get_table_schema("conversation_events")
        
        assert "conversation_id" in schema
        assert "tenant_id" in schema
        assert "created_at" in schema
        assert schema["created_at"] == "DateTime"

    def test_verify_schema(self):
        """Test schema verification."""
        analytics = ClickhouseAnalytics()
        
        assert analytics.verify_schema("conversation_events")
        assert analytics.verify_schema("llm_invocations")
        assert analytics.verify_schema("daily_kpis")
        assert not analytics.verify_schema("nonexistent_table")
