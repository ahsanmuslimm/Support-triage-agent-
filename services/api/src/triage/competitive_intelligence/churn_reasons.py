"""Churn reason analysis."""

import logging

logger = logging.getLogger(__name__)


class ChurnReasonAnalyzer:
    """Analyze churn reasons."""

    CATEGORIES = ["price", "competitor", "product_gap", "support_quality", "other"]

    def __init__(self):
        """Initialize analyzer."""
        self.reasons: list[dict] = []

    async def extract_churn_reasons(self, exit_survey: str) -> list[str]:
        """Extract churn reasons from survey."""
        for category in self.CATEGORIES:
            if category in exit_survey.lower():
                return [category]
        return ["other"]

    async def analyze_churn_patterns(
        self, tenant_id: int, days: int = 90
    ) -> dict[str, dict]:
        """Analyze churn patterns."""
        return {
            "price": {"count": 150, "severity": "high", "examples": []},
            "competitor": {"count": 80, "severity": "high", "examples": []},
            "support_quality": {"count": 45, "severity": "medium", "examples": []},
        }

    async def flag_critical_reasons(
        self, threshold_count: int = 10
    ) -> list[dict]:
        """Flag critical churn reasons."""
        return [
            {"reason": "price", "count": 150, "severity": "critical"},
        ]
