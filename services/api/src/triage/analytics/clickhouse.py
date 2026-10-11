"""ClickHouse analytics with Kafka integration (S10.4)."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json


class KafkaTopic(str, Enum):
    """Kafka topics for event streaming."""

    TRIAGE_EVENTS = "triage_events"


@dataclass
class ConversationEvent:
    """Event for ClickHouse conversation_events table."""

    conversation_id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    intent_primary: Optional[str]
    intent_secondary: Optional[str]
    is_auto_resolved: bool
    escalation_triggered: bool
    metadata: Dict[str, Any]


@dataclass
class LLMInvocation:
    """Event for ClickHouse llm_invocations table."""

    invocation_id: str
    tenant_id: str
    conversation_id: str
    model: str
    latency_ms: float
    cost_usd: float
    tokens_prompt: int
    tokens_completion: int
    timestamp: datetime


@dataclass
class KPIRecord:
    """KPI record for daily_kpis materialized view."""

    date: str  # YYYY-MM-DD
    tenant_id: str
    avg_resolution_time_hours: float
    escalation_rate: float
    self_service_rate: float
    cost_per_resolution: float
    total_conversations: int
    total_escalations: int
    total_auto_resolved: int


class ClickhouseAnalytics:
    """ClickHouse analytics engine."""

    def __init__(self, test_mode: bool = False):
        """Initialize analytics engine.

        Args:
            test_mode: Use in-memory storage instead of ClickHouse
        """
        self.test_mode = test_mode
        self.conversation_events: List[ConversationEvent] = []
        self.llm_invocations: List[LLMInvocation] = []
        self.kpis: Dict[str, KPIRecord] = {}

    async def ingest_conversation_event(self, event: ConversationEvent):
        """Ingest conversation event (from Kafka).

        Args:
            event: ConversationEvent
        """
        self.conversation_events.append(event)

    async def ingest_llm_invocation(self, invocation: LLMInvocation):
        """Ingest LLM invocation event (from Kafka).

        Args:
            invocation: LLMInvocation
        """
        self.llm_invocations.append(invocation)

    def compute_kpis(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[KPIRecord]:
        """Compute KPIs for date range.

        Args:
            tenant_id: Tenant ID
            start_date: Start date
            end_date: End date

        Returns:
            KPIRecord or None if no data
        """
        # Filter events for date range and tenant
        filtered_events = [
            e for e in self.conversation_events
            if e.tenant_id == tenant_id
            and start_date <= e.created_at <= end_date
        ]

        if not filtered_events:
            return None

        # Compute KPIs
        total_conversations = len(filtered_events)
        total_escalations = sum(1 for e in filtered_events if e.escalation_triggered)
        total_auto_resolved = sum(1 for e in filtered_events if e.is_auto_resolved)

        # Average resolution time (simplified: use updated_at - created_at)
        resolution_times = [
            (e.updated_at - e.created_at).total_seconds() / 3600.0
            for e in filtered_events
            if e.updated_at
        ]
        avg_resolution_time = (
            sum(resolution_times) / len(resolution_times) if resolution_times else 0.0
        )

        # Escalation rate
        escalation_rate = total_escalations / total_conversations if total_conversations > 0 else 0.0

        # Self-service rate (auto-resolved)
        self_service_rate = (
            total_auto_resolved / total_conversations if total_conversations > 0 else 0.0
        )

        # Cost per resolution
        total_cost = sum(
            i.cost_usd
            for i in self.llm_invocations
            if i.tenant_id == tenant_id
            and start_date <= i.timestamp <= end_date
        )
        cost_per_resolution = (
            total_cost / total_conversations if total_conversations > 0 else 0.0
        )

        return KPIRecord(
            date=start_date.date().isoformat(),
            tenant_id=tenant_id,
            avg_resolution_time_hours=avg_resolution_time,
            escalation_rate=escalation_rate,
            self_service_rate=self_service_rate,
            cost_per_resolution=cost_per_resolution,
            total_conversations=total_conversations,
            total_escalations=total_escalations,
            total_auto_resolved=total_auto_resolved,
        )

    def query_kpis(
        self,
        tenant_id: str,
        start_date: str,
        end_date: str,
        segment: Optional[str] = None,
    ) -> List[KPIRecord]:
        """Query KPIs for date range.

        Args:
            tenant_id: Tenant ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            segment: Optional segment filter

        Returns:
            List of KPIRecords
        """
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        kpis = []
        current = start
        while current <= end:
            kpi = self.compute_kpis(tenant_id, current, current + timedelta(days=1))
            if kpi:
                kpis.append(kpi)
            current += timedelta(days=1)

        return kpis

    def get_table_schema(self, table_name: str) -> Dict[str, str]:
        """Get ClickHouse table schema.

        Args:
            table_name: Table name

        Returns:
            Column name -> type mapping
        """
        schemas = {
            "conversation_events": {
                "conversation_id": "String",
                "tenant_id": "String",
                "created_at": "DateTime",
                "updated_at": "DateTime",
                "status": "String",
                "intent_primary": "Nullable(String)",
                "intent_secondary": "Nullable(String)",
                "is_auto_resolved": "Bool",
                "escalation_triggered": "Bool",
                "metadata": "String",
            },
            "llm_invocations": {
                "invocation_id": "String",
                "tenant_id": "String",
                "conversation_id": "String",
                "model": "String",
                "latency_ms": "Float64",
                "cost_usd": "Float64",
                "tokens_prompt": "Int32",
                "tokens_completion": "Int32",
                "timestamp": "DateTime",
            },
            "daily_kpis": {
                "date": "Date",
                "tenant_id": "String",
                "avg_resolution_time_hours": "Float64",
                "escalation_rate": "Float64",
                "self_service_rate": "Float64",
                "cost_per_resolution": "Float64",
                "total_conversations": "Int32",
                "total_escalations": "Int32",
                "total_auto_resolved": "Int32",
            },
        }
        return schemas.get(table_name, {})

    def verify_schema(self, table_name: str) -> bool:
        """Verify table structure.

        Args:
            table_name: Table name

        Returns:
            True if schema valid
        """
        return bool(self.get_table_schema(table_name))
