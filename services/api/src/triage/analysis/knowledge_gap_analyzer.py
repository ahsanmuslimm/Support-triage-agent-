"""S3.5: Knowledge Gap Analysis."""

import logging
from typing import List, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeGap:
    """Knowledge gap finding."""

    topic: str
    gap_score: float  # 0.0 (high coverage) to 1.0 (no coverage)
    suggested_article_title: str
    escalation_count: int


class KnowledgeGapAnalyzer:
    """Identify KB coverage gaps and recommend articles."""

    def __init__(self, intent_classifier=None, db_session=None):
        self.intent_classifier = intent_classifier
        self.db = db_session

    async def analyze_gaps(
        self, tenant_id: int, lookback_days: int = 7
    ) -> List[KnowledgeGap]:
        """
        Analyze queries from last N days and identify gaps.

        Returns:
            Top 10 gaps ranked by gap_score
        """
        if not self.db:
            return []

        try:
            # Fetch queries from last N days
            from datetime import datetime, timedelta

            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            queries = await self.db.query(
                """
                SELECT id, query_text, was_escalated FROM conversations
                WHERE tenant_id = $1 AND created_at >= $2
                """,
                tenant_id,
                cutoff,
            ).all()

            # Categorize queries
            category_stats = {}
            for q in queries:
                category = await self._categorize_query(q.query_text)

                if category not in category_stats:
                    category_stats[category] = {"total": 0, "escalated": 0}

                category_stats[category]["total"] += 1
                if q.was_escalated:
                    category_stats[category]["escalated"] += 1

            # Compute gaps
            gaps = []
            for category, stats in category_stats.items():
                coverage = 1.0 - (stats["escalated"] / stats["total"]) if stats["total"] > 0 else 0
                gap_score = 1.0 - coverage

                if gap_score > 0.1:  # Only gaps with meaningful coverage gaps
                    gaps.append(
                        KnowledgeGap(
                            topic=category,
                            gap_score=gap_score,
                            suggested_article_title=self._suggest_title(category),
                            escalation_count=stats["escalated"],
                        )
                    )

            # Sort by gap score, return top 10
            gaps.sort(key=lambda x: x.gap_score, reverse=True)
            return gaps[:10]

        except Exception as e:
            logger.error(f"Knowledge gap analysis failed: {e}")
            return []

    async def _categorize_query(self, query_text: str) -> str:
        """Categorize query using intent classifier or keyword matching."""
        if self.intent_classifier:
            try:
                intent = await self.intent_classifier.classify(query_text)
                return intent
            except Exception as e:
                logger.warning(f"Intent classification failed: {e}")

        # Fallback: keyword matching
        keywords = {
            "billing": ["charge", "refund", "invoice", "payment", "subscription"],
            "shipping": ["ship", "delivery", "tracking", "address"],
            "product": ["feature", "product", "issue", "bug", "error"],
            "account": ["password", "login", "account", "profile"],
        }

        query_lower = query_text.lower()
        for category, words in keywords.items():
            if any(word in query_lower for word in words):
                return category

        return "other"

    def _suggest_title(self, category: str) -> str:
        """Generate suggested KB article title."""
        suggestions = {
            "billing": "Billing & Payment Troubleshooting Guide",
            "shipping": "Shipping & Delivery: FAQ",
            "product": "Product Issues & Known Problems",
            "account": "Account Management & Security",
            "other": "General Support Articles",
        }
        return suggestions.get(category, f"Help with {category}")
