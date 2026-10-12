"""Market intelligence analyzer orchestrator."""

import logging

from .benchmarking import CompetitiveBenchmarker
from .churn_reasons import ChurnReasonAnalyzer
from .feature_requests import FeatureRequestAggregator
from .mentions import MentionTracker

logger = logging.getLogger(__name__)


class MarketIntelligenceAnalyzer:
    """Orchestrate market intelligence."""

    def __init__(self):
        """Initialize analyzer."""
        self.mentions = MentionTracker()
        self.feature_requests = FeatureRequestAggregator()
        self.churn_reasons = ChurnReasonAnalyzer()
        self.benchmarker = CompetitiveBenchmarker()

    async def analyze_market_intelligence(
        self, tenant_id: int
    ) -> dict:
        """Full market intelligence analysis."""
        return {
            "mentions": await self.mentions.monthly_mention_report(tenant_id, "2026-01"),
            "feature_requests": await self.feature_requests.aggregate_requests(tenant_id),
            "churn_patterns": await self.churn_reasons.analyze_churn_patterns(tenant_id),
        }
