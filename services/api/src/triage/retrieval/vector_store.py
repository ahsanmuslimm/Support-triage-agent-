"""In-memory vector store using embeddings and cosine similarity."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class SearchResult:
    """A single search result."""

    doc_id: str
    text: str
    score: float  # Cosine similarity in [0, 1]
    source: str = "vector"


class VectorStore:
    """In-memory vector store with cosine similarity search."""

    def __init__(self, embedding_model=None):
        """Initialize vector store.

        Args:
            embedding_model: Embedding model (e.g., SentenceTransformer).
                           If None, will try to load default.
        """
        self.documents: List[Tuple[str, str]] = []  # (doc_id, text)
        self.embeddings: Optional[np.ndarray] = None
        self.embedding_model = embedding_model
        self._init_embedding_model()

    def _init_embedding_model(self):
        """Initialize embedding model lazily."""
        if self.embedding_model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            log.info("vector_store_embedding_model_loaded", model="all-MiniLM-L6-v2")
        except Exception as e:
            log.warning("vector_store_embedding_model_unavailable", error=str(e))
            self.embedding_model = None

    def add_documents(self, documents: List[Tuple[str, str]]) -> None:
        """Add documents to store.

        Args:
            documents: List of (doc_id, text) tuples
        """
        self.documents.extend(documents)

        # Re-embed all documents
        try:
            if self.embedding_model:
                texts = [text for _, text in self.documents]
                embeddings_list = self.embedding_model.encode(texts, convert_to_numpy=True)
                self.embeddings = np.array(embeddings_list)
                log.info("vector_store_documents_added", count=len(documents), total_documents=len(self.documents))
        except Exception as e:
            log.error("vector_store_embedding_error", error=str(e))
            self.embeddings = None

    def search(self, query: str, k: int = 5) -> List[SearchResult]:
        """Search for documents similar to query.

        Args:
            query: Query text
            k: Number of results to return

        Returns:
            List of SearchResult objects ranked by similarity
        """
        if not self.documents or not self.embedding_model:
            return []

        try:
            # Embed query
            query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)

            # Compute cosine similarity
            similarities = self._cosine_similarity(query_embedding, self.embeddings)

            # Get top k
            top_indices = np.argsort(similarities)[::-1][:k]

            results = []
            for idx in top_indices:
                if similarities[idx] < 0:  # Skip negative similarities
                    continue
                doc_id, text = self.documents[idx]
                results.append(
                    SearchResult(
                        doc_id=doc_id,
                        text=text,
                        score=float(similarities[idx]),
                    )
                )

            log.debug("vector_search_complete", query_length=len(query), results_count=len(results))
            return results

        except Exception as e:
            log.error("vector_search_error", error=str(e))
            return []

    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2_array: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between vec1 and each row of vec2_array.

        Args:
            vec1: Query embedding
            vec2_array: Document embeddings (N x D)

        Returns:
            Similarity scores
        """
        # Normalize
        vec1_norm = vec1 / (np.linalg.norm(vec1) + 1e-8)
        vec2_norms = vec2_array / (np.linalg.norm(vec2_array, axis=1, keepdims=True) + 1e-8)

        # Cosine similarity
        similarities = np.dot(vec2_norms, vec1_norm)
        return similarities
