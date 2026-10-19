"""Knowledge worker loop: periodically sync intent embeddings."""

import asyncio
import os

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from triage.db import create_engine

from .sync import collect_examples, sync_embeddings

log = structlog.get_logger()

SYNC_INTERVAL = float(os.environ.get("KNOWLEDGE_SYNC_INTERVAL", "300"))
MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _load_encoder():
    """Load the sentence-transformer model (downloads on first use)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    return lambda texts: model.encode(texts, convert_to_numpy=True)


async def run_forever() -> None:
    """Periodically recompute per-intent centroid embeddings."""
    engine = create_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    log.info("knowledge_worker_started", interval=SYNC_INTERVAL, model=MODEL_NAME)
    try:
        while True:
            try:
                async with factory() as session:
                    if await collect_examples(session):
                        # Lazy-load the model only when there is work to do
                        encode = _load_encoder()
                        await sync_embeddings(session, encode)
            except Exception:
                log.exception("knowledge_sync_error")
            await asyncio.sleep(SYNC_INTERVAL)
    finally:
        await engine.dispose()
