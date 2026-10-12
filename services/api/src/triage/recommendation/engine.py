"""Recommendation engine orchestrator."""

import logging

from .ab_testing import ABTestingFramework
from .collaborative import CollaborativeFilter
from .models import ABTestVariant, RecommendationResult
from .semantic_ranker import SemanticRanker
from .tfidf_ranker import TFIDFRanker

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Orchestrates all recommendation methods."""

    def __init__(self):
        """Initialize engine."""
        self.tfidf = TFIDFRanker()
        self.semantic = SemanticRanker()
        self.collaborative = CollaborativeFilter()
        self.ab_test = ABTestingFramework()

    async def recommend_articles(
        self,
        customer_id: int,
        tenant_id: int,
        query: str,
        variant: ABTestVariant | None = None,
        top_k: int = 5,
    ) -> list[RecommendationResult]:
        """Recommend KB articles for customer."""
        if variant is None:
            variant = await self.ab_test.get_variant_for_customer(customer_id)

        results = []

        if variant == ABTestVariant.CONTROL:
            # TF-IDF only
            ranked = await self.tfidf.rank_articles(query, top_k=top_k)
            for rank, (article_id, score) in enumerate(ranked, 1):
                results.append(RecommendationResult(
                    article_id=article_id,
                    title=f"Article {article_id}",
                    rank=rank,
                    score=score,
                    reason="tfidf_match",
                ))

        elif variant == ABTestVariant.PERSONALIZED:
            # TF-IDF + semantic re-ranking
            ranked = await self.tfidf.rank_articles(query, top_k=top_k * 2)
            reranked = await self.semantic.rerank_tfidf_results(query, ranked)
            for rank, (article_id, score) in enumerate(reranked[:top_k], 1):
                results.append(RecommendationResult(
                    article_id=article_id,
                    title=f"Article {article_id}",
                    rank=rank,
                    score=score,
                    reason="semantic_personalized",
                ))

        else:  # COLLABORATIVE
            # Collaborative filtering
            collab_recs = await self.collaborative.recommend_for_customer(customer_id, top_k)
            for rank, (article_id, score) in enumerate(collab_recs, 1):
                results.append(RecommendationResult(
                    article_id=article_id,
                    title=f"Article {article_id}",
                    rank=rank,
                    score=score,
                    reason="collaborative_filtering",
                ))

        return results
