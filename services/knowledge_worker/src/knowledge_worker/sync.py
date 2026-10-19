"""Embedding sync logic: intent examples -> per-intent centroid embeddings."""

import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from triage.models.orm import IntentEmbedding as IntentEmbeddingORM
from triage.models.orm import IntentExample as IntentExampleORM

log = structlog.get_logger()

EncodeFn = Callable[[list[str]], Any]


def compute_centroids(
    examples: dict[tuple[uuid.UUID, str], list[str]],
    encode: EncodeFn,
) -> dict[tuple[uuid.UUID, str], list[float]]:
    """Compute one centroid embedding per (tenant, intent) group."""
    centroids: dict[tuple[uuid.UUID, str], list[float]] = {}
    for key, texts in examples.items():
        if not texts:
            continue
        vectors = np.asarray(encode(texts), dtype=float)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        centroids[key] = np.mean(vectors, axis=0).tolist()
    return centroids


async def collect_examples(session: AsyncSession) -> dict[tuple[uuid.UUID, str], list[str]]:
    """Group intent example texts by (tenant, intent)."""
    result = await session.execute(
        select(
            IntentExampleORM.tenant_id,
            IntentExampleORM.intent_name,
            IntentExampleORM.example_text,
        )
    )
    grouped: dict[tuple[uuid.UUID, str], list[str]] = defaultdict(list)
    for tenant_id, intent_name, text in result.all():
        grouped[(tenant_id, intent_name)].append(text)
    return dict(grouped)


async def sync_embeddings(session: AsyncSession, encode: EncodeFn) -> int:
    """Recompute and upsert per-intent centroid embeddings. Returns rows written."""
    examples = await collect_examples(session)
    if not examples:
        return 0

    centroids = compute_centroids(examples, encode)
    now = datetime.now(UTC)
    for (tenant_id, intent_name), vector in centroids.items():
        existing = await session.get(IntentEmbeddingORM, (tenant_id, intent_name))
        if existing is not None:
            existing.embedding = vector
            existing.updated_at = now
        else:
            session.add(
                IntentEmbeddingORM(tenant_id=tenant_id, intent_name=intent_name, embedding=vector)
            )
    await session.commit()
    log.info("intent_embeddings_synced", intents=len(centroids))
    return len(centroids)
