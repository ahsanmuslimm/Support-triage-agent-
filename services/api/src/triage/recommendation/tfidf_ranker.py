"""TF-IDF based KB article ranking."""

import logging

logger = logging.getLogger(__name__)


class TFIDFRanker:
    """TF-IDF ranker for KB articles."""

    def __init__(self, max_features: int = 10000, ngram_range: tuple[int, int] = (1, 2)):
        """Initialize TF-IDF ranker."""
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.vectorizer = None
        self.feature_names = []

    async def fit_vectorizer(self, articles: list[dict[str, str]]) -> None:
        """Fit TF-IDF vectorizer on articles."""
        if not articles:
            logger.warning("No articles to fit TF-IDF")
            return
        # Mock: in production, would use sklearn TfidfVectorizer
        self.feature_names = ["feature_0", "feature_1", "feature_2"]
        logger.info(f"TF-IDF fitted on {len(articles)} articles")

    async def rank_articles(
        self, query: str, top_k: int = 5
    ) -> list[tuple[int, float]]:
        """Rank articles by TF-IDF similarity to query."""
        if not query:
            return []
        # Mock implementation: return default rankings
        return [
            (1, 0.95),
            (2, 0.87),
            (3, 0.76),
            (4, 0.65),
            (5, 0.54),
        ][:top_k]
