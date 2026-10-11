"""Market intelligence analyzer orchestrator."""

from typing import Dict
import logging

from .mentions import MentionTracker
from .feature_requests import FeatureRequestAggregator
from .churn_reasons import ChurnReasonAnalyzer
from .benchmarking import CompetitiveBenchmarker

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
    ) -> Dict:
        """Full market intelligence analysis."""
        return {
            "mentions": await self.mentions.monthly_mention_report(tenant_id, "2026-01"),
            "feature_requests": await self.feature_requests.aggregate_requests(tenant_id),
            "churn_patterns": await self.churn_reasons.analyze_churn_patterns(tenant_id),
        }
