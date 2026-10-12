"""Multilingual KB retrieval with cross-language search."""

from dataclasses import dataclass

import structlog

log = structlog.get_logger()


@dataclass
class KBArticle:
    """Knowledge base article."""

    id: str
    """Article ID."""

    title: str
    """Article title."""

    content: str
    """Article body."""

    language: str
    """ISO 639-1 language code."""

    tags: list[str] = None
    """Article tags."""

    embedding: list[float] | None = None
    """Dense embedding vector."""

    relevance_score: float = 0.0
    """Relevance score (0-1) for retrieval."""

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class MultilingualRetriever:
    """Retrieve KB articles in customer's language or cross-language."""

    def __init__(self, kb_articles: list[KBArticle] = None) -> None:
        """Initialize retriever.

        Args:
            kb_articles: List of KB articles indexed in embedding space.
        """
        self.kb_articles = kb_articles or []
        self.language_index: dict[str, list[KBArticle]] = self._build_language_index()

    def _build_language_index(self) -> dict[str, list[KBArticle]]:
        """Build index of articles by language.

        Returns:
            Dict[str, List[KBArticle]]: Articles grouped by language.
        """
        index: dict[str, list[KBArticle]] = {}
        for article in self.kb_articles:
            lang = article.language
            if lang not in index:
                index[lang] = []
            index[lang].append(article)
        return index

    async def retrieve(
        self,
        query: str,
        customer_language: str,
        top_k: int = 5,
        cross_language: bool = True,
    ) -> list[KBArticle]:
        """Retrieve KB articles matching query.

        Args:
            query: Customer query in their language.
            customer_language: ISO 639-1 language code of customer.
            top_k: Number of results to return.
            cross_language: If True, search across all languages using multilingual embedding.

        Returns:
            List[KBArticle]: Top-K articles ranked by relevance.
        """
        try:
            log.info(
                "retrieval_start",
                query_chars=len(query),
                language=customer_language,
                cross_language=cross_language,
            )

            # Get query embedding (multilingual-e5)
            query_embedding = await self._embed_text(query)

            if cross_language:
                # Search across all articles
                candidates = self.kb_articles
            else:
                # Search in customer's language only
                candidates = self.language_index.get(customer_language, [])

            # Rank by similarity
            results = []
            for article in candidates:
                if article.embedding:
                    similarity = self._cosine_similarity(query_embedding, article.embedding)
                    article.relevance_score = similarity
                    results.append(article)

            # Sort by relevance
            results.sort(key=lambda x: x.relevance_score, reverse=True)

            # Prioritize customer's language if cross-language search
            if cross_language:
                results = self._prioritize_language(results, customer_language)

            log.info("retrieval_complete", results_count=len(results), top_k=top_k)

            return results[:top_k]

        except Exception as e:
            log.error("retrieval_error", error=str(e))
            return []

    def _prioritize_language(
        self,
        articles: list[KBArticle],
        target_language: str,
    ) -> list[KBArticle]:
        """Reorder results to prioritize target language.

        Args:
            articles: Articles with relevance scores.
            target_language: Target language code.

        Returns:
            List[KBArticle]: Reordered articles.
        """
        # Split into target language and other
        target_lang_articles = [a for a in articles if a.language == target_language]
        other_lang_articles = [a for a in articles if a.language != target_language]

        # Interleave: 2 target lang, then 1 other, etc
        result = []
        for i in range(max(len(target_lang_articles), len(other_lang_articles))):
            if i < len(target_lang_articles):
                result.append(target_lang_articles[i])
            if i < len(other_lang_articles):
                result.append(other_lang_articles[i])

        return result

    async def _embed_text(self, text: str) -> list[float]:
        """Generate embedding for text using multilingual-e5.

        Args:
            text: Text to embed.

        Returns:
            List[float]: Embedding vector.
        """
        try:
            # In real implementation, use sentence-transformers multilingual-e5-small
            # from sentence_transformers import SentenceTransformer
            # model = SentenceTransformer("intfloat/multilingual-e5-small")
            # embedding = model.encode(text).tolist()

            # Simulated embedding
            import hashlib
            hash_obj = hashlib.md5(text.encode())
            hash_hex = hash_obj.hexdigest()
            # Generate pseudo-embedding from hash
            embedding = [float(int(hash_hex[i:i+2], 16)) / 255.0 for i in range(0, len(hash_hex), 2)]
            return embedding[:384]  # multilingual-e5-small dimension

        except Exception as e:
            log.error("embedding_error", error=str(e))
            return [0.0] * 384

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            float: Similarity score (0-1).
        """
        try:
            import math

            if not vec1 or not vec2 or len(vec1) != len(vec2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        except Exception as e:
            log.error("similarity_error", error=str(e))
            return 0.0

    def get_language_statistics(self) -> dict[str, int]:
        """Get count of articles by language.

        Returns:
            Dict[str, int]: Article count per language.
        """
        stats = {}
        for lang, articles in self.language_index.items():
            stats[lang] = len(articles)
        return stats
