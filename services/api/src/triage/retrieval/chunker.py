"""Document chunking with overlap for RAG pipeline."""

from dataclasses import dataclass
from typing import List, Optional
import re
import structlog

log = structlog.get_logger()


@dataclass
class Chunk:
    """A single chunk of a document."""

    doc_id: str
    text: str
    start_idx: int  # Start position in original document
    end_idx: int  # End position in original document
    chunk_num: int  # Chunk sequence number
    token_count: Optional[int] = None  # Estimated token count


class DocumentChunker:
    """Chunk documents into fixed-size overlapping chunks."""

    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        """Initialize chunker.

        Args:
            chunk_size: Target tokens per chunk
            overlap: Overlap tokens between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc_id: str, text: str) -> List[Chunk]:
        """Chunk a document into overlapping chunks.

        Attempts to preserve sentence boundaries.

        Args:
            doc_id: Document identifier
            text: Document text to chunk

        Returns:
            List of Chunk objects
        """
        if not text or len(text.strip()) == 0:
            return []

        # Split by sentences (simple approach)
        sentences = self._split_sentences(text)

        chunks: List[Chunk] = []
        current_chunk_text = ""
        current_chunk_start = 0
        chunk_num = 0

        for i, sentence in enumerate(sentences):
            test_text = current_chunk_text + " " + sentence if current_chunk_text else sentence
            est_tokens = self._estimate_tokens(test_text)

            if est_tokens > self.chunk_size and current_chunk_text:
                # Current chunk is full; save it
                chunk = Chunk(
                    doc_id=doc_id,
                    text=current_chunk_text.strip(),
                    start_idx=current_chunk_start,
                    end_idx=current_chunk_start + len(current_chunk_text),
                    chunk_num=chunk_num,
                    token_count=self._estimate_tokens(current_chunk_text),
                )
                chunks.append(chunk)
                chunk_num += 1

                # Restart with overlap: go back by overlap tokens worth of text
                # Simple approach: restart from current sentence with some previous context
                overlap_text = " ".join(
                    sentences[max(0, i - 2) : i]  # 2-3 sentences of overlap
                )
                current_chunk_text = overlap_text
                current_chunk_start = max(0, current_chunk_start + len(current_chunk_text) - len(overlap_text))

            # Add sentence to current chunk
            current_chunk_text = test_text

        # Save final chunk
        if current_chunk_text.strip():
            chunk = Chunk(
                doc_id=doc_id,
                text=current_chunk_text.strip(),
                start_idx=current_chunk_start,
                end_idx=current_chunk_start + len(current_chunk_text),
                chunk_num=chunk_num,
                token_count=self._estimate_tokens(current_chunk_text),
            )
            chunks.append(chunk)

        log.info("document_chunked", doc_id=doc_id, chunk_count=len(chunks), total_tokens=sum(c.token_count or 0 for c in chunks))

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into sentences.

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Simple regex-based splitting
        # Split on . ! ? followed by space
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (simple word-based).

        In production: use tiktoken or other accurate tokenizer.
        """
        # Simple heuristic: ~1.3 tokens per word
        words = text.split()
        return int(len(words) * 1.3)
