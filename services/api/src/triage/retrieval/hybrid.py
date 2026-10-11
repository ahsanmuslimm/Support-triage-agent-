"""Hybrid retrieval with RRF (Reciprocal Rank Fusion)."""

from dataclasses import dataclass
from typing import List, Dict, Optional
import structlog

from triage.retrieval.vector_store import VectorStore, SearchResult as VectorResult
from triage.retrieval.bm25_search import BM25Search, BM25Result

log = structlog.get_logger()


@dataclass
class RetrievalResult:
    """A single result from hybrid retrieval."""

    doc_id: str
    text: str
    score: float  # Final RRF-fused score
    source: str  # "vector", "bm25", or "both"


class HybridRetriever:
    """Hybrid retrieval combining vector search and BM25 via RRF."""

    def __init__(self, k_rrf: int = 60, vector_weight: float = 0.5, bm25_weight: float = 0.5):
        """Initialize hybrid retriever.

        Args:
            k_rrf: Parameter for RRF formula (1 / (k + rank))
            vector_weight: Weight for vector search results
            bm25_weight: Weight for BM25 results
        """
        self.k_rrf = k_rrf
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight

        self.vector_store = VectorStore()
        self.bm25_search = BM25Search()

    def add_documents(self, documents: List[tuple[str, str]]) -> None:
        """Add documents to both search indices.

        Args:
            documents: List of (doc_id, text) tuples
        """
        self.vector_store.add_documents(documents)
        self.bm25_search.add_documents(documents)
        log.info("hybrid_retriever_documents_added", count=len(documents))

    async def retrieve(self, query: str, k: int = 5) -> List[RetrievalResult]:
        """Retrieve documents using hybrid search with RRF fusion.

        Args:
            query: Query text
            k: Number of results to return

        Returns:
            List of RetrievalResult objects ranked by fused score
        """
        # Run searches in parallel (using simple sequential for now)
        vector_results = self.vector_store.search(query, k=k * 2)  # Get more for fusion
        bm25_results = self.bm25_search.search(query, k=k * 2)

        # Fuse results using RRF
        fused = self._rrf_fusion(vector_results, bm25_results, k)

        log.debug(
            "hybrid_retrieve_complete",
            query_length=len(query),
            vector_count=len(vector_results),
            bm25_count=len(bm25_results),
            fused_count=len(fused),
        )

        return fused

    def _rrf_fusion(
        self, vector_results: List[VectorResult], bm25_results: List[BM25Result], k: int
    ) -> List[RetrievalResult]:
        """Fuse results using Reciprocal Rank Fusion.

        RRF(d) = sum over search systems s of (1 / (k + rank_s(d)))

        Args:
            vector_results: Results from vector search
            bm25_results: Results from BM25 search
            k: Target results to return

        Returns:
            List of fused results
        """
        # Map doc_id -> (text, fused_score, sources)
        doc_scores: Dict[str, tuple[str, float, set]] = {}

        # Add vector results
        for rank, result in enumerate(vector_results):
            rrf_score = 1.0 / (self.k_rrf + rank + 1)
            weighted_score = rrf_score * self.vector_weight

            if result.doc_id not in doc_scores:
                doc_scores[result.doc_id] = (result.text, 0.0, set())

            text, current_score, sources = doc_scores[result.doc_id]
            doc_scores[result.doc_id] = (text, current_score + weighted_score, sources | {"vector"})

        # Add BM25 results
        for rank, result in enumerate(bm25_results):
            rrf_score = 1.0 / (self.k_rrf + rank + 1)
            weighted_score = rrf_score * self.bm25_weight

            if result.doc_id not in doc_scores:
                doc_scores[result.doc_id] = (result.text, 0.0, set())

            text, current_score, sources = doc_scores[result.doc_id]
            doc_scores[result.doc_id] = (text, current_score + weighted_score, sources | {"bm25"})

        # Sort by fused score and take top k
        sorted_docs = sorted(
            [
                (doc_id, text, score, sources)
                for doc_id, (text, score, sources) in doc_scores.items()
            ],
            key=lambda x: x[2],
            reverse=True,
        )

        results = []
        for doc_id, text, score, sources in sorted_docs[:k]:
            source_str = ",".join(sorted(sources))
            results.append(
                RetrievalResult(
                    doc_id=doc_id,
                    text=text,
                    score=score,
                    source=source_str,
                )
            )

        return results
