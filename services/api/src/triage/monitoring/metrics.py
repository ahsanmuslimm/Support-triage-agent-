"""Prometheus metrics collection for Sprint 4 monitoring."""

import logging
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Namespace
NAMESPACE = "triage"

# Escalation metrics
escalation_count = Counter(
    f"{NAMESPACE}_escalation_count",
    "Total escalations",
    ["priority", "tenant_id"],
)

escalation_rate = Gauge(
    f"{NAMESPACE}_escalation_rate",
    "Escalations per minute",
    ["tenant_id"],
)

# Resolution metrics
resolution_time = Histogram(
    f"{NAMESPACE}_resolution_time_seconds",
    "Time to resolve escalation",
    ["autonomy_level"],
    buckets=(10, 30, 60, 120, 300, 600, 1800, 3600),
)

# Cost metrics
cost_per_resolution = Gauge(
    f"{NAMESPACE}_cost_per_resolution_usd",
    "Cost per resolved ticket",
    ["tenant_id"],
)

# SLA metrics
sla_breach_count = Counter(
    f"{NAMESPACE}_sla_breach_count",
    "SLA breaches",
    ["priority", "tenant_id"],
)

# Anomaly detection metrics
anomaly_detection_latency = Histogram(
    f"{NAMESPACE}_anomaly_detection_latency_ms",
    "Anomaly detection latency",
    ["signal_type"],
    buckets=(10, 50, 100, 500, 1000, 2000),
)

# Escalation routing metrics
escalation_routing_latency = Histogram(
    f"{NAMESPACE}_escalation_routing_latency_ms",
    "Escalation routing latency",
    ["channel"],
    buckets=(100, 500, 1000, 2000, 5000),
)

# Context quality metrics
context_quality_score = Gauge(
    f"{NAMESPACE}_context_quality_score",
    "Handoff context quality (0-1)",
    ["tenant_id"],
)


class MetricsCollector:
    """Collects metrics for Sprint 4."""

    @staticmethod
    async def record_escalation(tenant_id: str, priority: str) -> None:
        """
        Record an escalation event.
        
        Args:
            tenant_id: Tenant ID
            priority: Priority level (p0, p1, p2, p3)
        """
        escalation_count.labels(priority=priority, tenant_id=tenant_id).inc()
        logger.debug(f"Recorded escalation: tenant={tenant_id} priority={priority}")

    @staticmethod
    async def record_resolution(resolution_time_sec: float, autonomy_level: int) -> None:
        """
        Record a resolution event.
        
        Args:
            resolution_time_sec: Time to resolution in seconds
            autonomy_level: Autonomy level (0-5)
        """
        resolution_time.labels(autonomy_level=str(autonomy_level)).observe(resolution_time_sec)
        logger.debug(f"Recorded resolution: time={resolution_time_sec}s autonomy={autonomy_level}")

    @staticmethod
    async def record_cost(tenant_id: str, cost_usd: float) -> None:
        """
        Record cost for resolution.
        
        Args:
            tenant_id: Tenant ID
            cost_usd: Cost in USD
        """
        cost_per_resolution.labels(tenant_id=tenant_id).set(cost_usd)

    @staticmethod
    async def record_sla_breach(tenant_id: str, priority: str) -> None:
        """
        Record an SLA breach.
        
        Args:
            tenant_id: Tenant ID
            priority: Priority level
        """
        sla_breach_count.labels(priority=priority, tenant_id=tenant_id).inc()

    @staticmethod
    async def record_anomaly_detection(signal_type: str, latency_ms: float) -> None:
        """
        Record anomaly detection latency.
        
        Args:
            signal_type: Type of signal
            latency_ms: Latency in milliseconds
        """
        anomaly_detection_latency.labels(signal_type=signal_type).observe(latency_ms)

    @staticmethod
    async def record_routing(channel: str, latency_ms: float) -> None:
        """
        Record escalation routing latency.
        
        Args:
            channel: Routing channel (slack, email, pagerduty, webhook)
            latency_ms: Latency in milliseconds
        """
        escalation_routing_latency.labels(channel=channel).observe(latency_ms)

    @staticmethod
    async def record_context_quality(tenant_id: str, quality_score: float) -> None:
        """
        Record context quality score.
        
        Args:
            tenant_id: Tenant ID
            quality_score: Quality score (0-1)
        """
        context_quality_score.labels(tenant_id=tenant_id).set(quality_score)
