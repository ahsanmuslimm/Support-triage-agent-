"""BM25 keyword search for RAG pipeline."""

from dataclasses import dataclass
from typing import List, Optional
import structlog

log = structlog.get_logger()


@dataclass
class BM25Result:
    """A single BM25 search result."""

    doc_id: str
    text: str
    score: float  # BM25 score
    source: str = "bm25"


class BM25Search:
    """BM25 keyword search using rank_bm25 library."""

    def __init__(self):
        """Initialize BM25 search."""
        self.documents: List[tuple[str, str]] = []  # (doc_id, text)
        self.bm25_index = None
        self._init_bm25()

    def _init_bm25(self):
        """Initialize BM25 library."""
        try:
            from rank_bm25 import BM25Okapi
            self.BM25Okapi = BM25Okapi
            log.info("bm25_initialized")
        except ImportError:
            log.warning("rank_bm25_not_available; BM25 search disabled")
            self.BM25Okapi = None

    def add_documents(self, documents: List[tuple[str, str]]) -> None:
        """Add documents to BM25 index.

        Args:
            documents: List of (doc_id, text) tuples
        """
        self.documents.extend(documents)

        # Rebuild index
        try:
            if self.BM25Okapi:
                # Tokenize documents
                corpus = [self._tokenize(text) for _, text in self.documents]
                self.bm25_index = self.BM25Okapi(corpus)
                log.info("bm25_index_built", document_count=len(self.documents))
        except Exception as e:
            log.error("bm25_index_error", error=str(e))

    def search(self, query: str, k: int = 5) -> List[BM25Result]:
        """Search for documents matching query.

        Args:
            query: Query text
            k: Number of results to return

        Returns:
            List of BM25Result objects ranked by score
        """
        if not self.documents or not self.bm25_index:
            return []

        try:
            # Tokenize query
            query_tokens = self._tokenize(query)

            # Get BM25 scores
            scores = self.bm25_index.get_scores(query_tokens)

            # Get top k
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

            results = []
            for idx in top_indices:
                if scores[idx] <= 0:
                    continue
                doc_id, text = self.documents[idx]
                results.append(
                    BM25Result(
                        doc_id=doc_id,
                        text=text,
                        score=scores[idx],
                    )
                )

            log.debug("bm25_search_complete", query_length=len(query), results_count=len(results))
            return results

        except Exception as e:
            log.error("bm25_search_error", error=str(e))
            return []

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple tokenization."""
        return text.lower().split()
