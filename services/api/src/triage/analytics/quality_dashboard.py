"""AI Quality Dashboard & ROI tracking (S10.5)."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class QualityMetrics:
    """AI quality metrics."""

    intent_top1_accuracy: float  # 0-1
    entity_f1_score: float  # 0-1
    groundedness: float  # 0-1 (model outputs match KB)
    escalation_rate: float  # 0-1
    false_resolution_rate: float  # 0-1 (auto-resolved but human escalated)
    cost_per_resolution: float  # USD


@dataclass
class ROIReport:
    """Return on investment report."""

    period_start: str  # ISO date
    period_end: str
    total_cost: float  # USD
    deflection_count: int  # Conversations self-resolved
    faster_resolution_count: int  # Human-resolved faster due to AI help
    total_value: float  # USD (deflection*50 + faster_resolution*10)
    net_roi: float  # USD (total_value - total_cost)
    payback_period_days: float | None  # Days to break even


class QualityDashboard:
    """Track AI quality metrics and ROI."""

    def __init__(self):
        self.metrics_history: list[dict[str, Any]] = []
        self.roi_reports: list[ROIReport] = []

    def compute_quality_metrics(
        self,
        intent_predictions: list[dict[str, float]],
        entity_extractions: list[dict[str, float]],
        escalations: list[bool],
        false_resolutions: list[bool],
        costs: list[float],
    ) -> QualityMetrics:
        """Compute quality metrics from sample data.

        Args:
            intent_predictions: List of {predicted: bool} dicts
            entity_extractions: List of {precision, recall} dicts
            escalations: List of escalation flags
            false_resolutions: List of false resolution flags
            costs: List of costs

        Returns:
            QualityMetrics
        """
        # Intent top-1 accuracy
        intent_accuracy = (
            sum(p["predicted"] for p in intent_predictions) / len(intent_predictions)
            if intent_predictions
            else 0.0
        )

        # Entity F1 (average of precision and recall)
        entity_f1 = 0.0
        if entity_extractions:
            f1_scores = []
            for e in entity_extractions:
                p = e.get("precision", 0)
                r = e.get("recall", 0)
                f1 = 2 * (p * r) / (p + r) if (p + r) > 0 else 0
                f1_scores.append(f1)
            entity_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

        # Escalation rate
        escalation_rate = (
            sum(escalations) / len(escalations) if escalations else 0.0
        )

        # False resolution rate
        false_resolution_rate = (
            sum(false_resolutions) / len(false_resolutions) if false_resolutions else 0.0
        )

        # Cost per resolution
        cost_per_resolution = (
            sum(costs) / len(costs) if costs else 0.0
        )

        # Groundedness (simplified: absence of escalations = well-grounded)
        groundedness = 1.0 - escalation_rate

        return QualityMetrics(
            intent_top1_accuracy=intent_accuracy,
            entity_f1_score=entity_f1,
            groundedness=groundedness,
            escalation_rate=escalation_rate,
            false_resolution_rate=false_resolution_rate,
            cost_per_resolution=cost_per_resolution,
        )

    def record_metrics(
        self,
        tenant_id: str,
        period_start: datetime,
        metrics: QualityMetrics,
    ):
        """Record quality metrics snapshot.

        Args:
            tenant_id: Tenant ID
            period_start: Period start
            metrics: QualityMetrics
        """
        self.metrics_history.append({
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            "period_start": period_start.isoformat(),
            **asdict(metrics),
        })

    def compute_roi(
        self,
        period_start: datetime,
        period_end: datetime,
        total_cost: float,
        deflection_count: int,
        faster_resolution_count: int,
    ) -> ROIReport:
        """Compute ROI report.

        Args:
            period_start: Period start
            period_end: Period end
            total_cost: Total cost (USD)
            deflection_count: Self-resolved conversations
            faster_resolution_count: Human conversations improved by AI

        Returns:
            ROIReport
        """
        # Value calculation
        deflection_value = deflection_count * 50  # $50 per deflection
        faster_resolution_value = faster_resolution_count * 10  # $10 per faster resolution
        total_value = deflection_value + faster_resolution_value

        # ROI
        net_roi = total_value - total_cost

        # Payback period
        daily_value = total_value / max((period_end - period_start).days, 1)
        payback_period_days = (
            total_cost / daily_value if daily_value > 0 else None
        )

        report = ROIReport(
            period_start=period_start.date().isoformat(),
            period_end=period_end.date().isoformat(),
            total_cost=total_cost,
            deflection_count=deflection_count,
            faster_resolution_count=faster_resolution_count,
            total_value=total_value,
            net_roi=net_roi,
            payback_period_days=payback_period_days,
        )

        self.roi_reports.append(report)
        return report

    def export_pdf(self, report: ROIReport) -> bytes:
        """Export ROI report as PDF.

        Args:
            report: ROIReport

        Returns:
            PDF bytes (stub implementation)
        """
        # Stub: would use reportlab or similar
        pdf_content = f"""
        ROI Report: {report.period_start} to {report.period_end}
        
        Costs:
        - Total Cost: ${report.total_cost:.2f}
        
        Value:
        - Deflections: {report.deflection_count} x $50 = ${report.deflection_count * 50:.2f}
        - Faster Resolutions: {report.faster_resolution_count} x $10 = ${report.faster_resolution_count * 10:.2f}
        - Total Value: ${report.total_value:.2f}
        
        ROI:
        - Net ROI: ${report.net_roi:.2f}
        - Payback Period: {report.payback_period_days:.1f} days if applicable
        """.strip()
        return pdf_content.encode("utf-8")

    def get_trending_metrics(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> dict[str, list[float]]:
        """Get trending metrics over time.

        Args:
            tenant_id: Tenant ID
            days: Number of days to look back

        Returns:
            Dict of metric_name -> [values]
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        relevant = [
            m for m in self.metrics_history
            if m["tenant_id"] == tenant_id
            and datetime.fromisoformat(m["timestamp"]) >= cutoff
        ]

        if not relevant:
            return {}

        return {
            "intent_top1_accuracy": [m["intent_top1_accuracy"] for m in relevant],
            "entity_f1_score": [m["entity_f1_score"] for m in relevant],
            "groundedness": [m["groundedness"] for m in relevant],
            "escalation_rate": [m["escalation_rate"] for m in relevant],
            "false_resolution_rate": [m["false_resolution_rate"] for m in relevant],
            "cost_per_resolution": [m["cost_per_resolution"] for m in relevant],
        }
