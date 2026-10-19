"""Tests for knowledge worker embedding sync (no DB, no ML model required)."""

import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from knowledge_worker.sync import compute_centroids

pytestmark = pytest.mark.unit


def fake_encode(texts: list[str]) -> np.ndarray:
    """Deterministic pseudo-embeddings derived from text length and content."""
    return np.array([[len(t), sum(ord(c) for c in t) % 97] for t in texts], dtype=float)


class TestComputeCentroids:
    def test_single_group_centroid_is_mean(self):
        tenant = uuid.uuid4()
        examples = {(tenant, "refund"): ["aa", "aaa"]}
        centroids = compute_centroids(examples, fake_encode)
        expected = np.mean(fake_encode(["aa", "aaa"]), axis=0).tolist()
        assert centroids[(tenant, "refund")] == pytest.approx(expected)

    def test_groups_are_independent(self):
        tenant = uuid.uuid4()
        examples = {(tenant, "refund"): ["aa"], (tenant, "billing"): ["bbbb"]}
        centroids = compute_centroids(examples, fake_encode)
        assert len(centroids) == 2
        assert centroids[(tenant, "refund")] == pytest.approx(fake_encode(["aa"])[0].tolist())

    def test_empty_group_skipped(self):
        tenant = uuid.uuid4()
        examples = {(tenant, "refund"): []}
        assert compute_centroids(examples, fake_encode) == {}

    def test_single_text_passes_through(self):
        tenant = uuid.uuid4()
        examples = {(tenant, "question"): ["hello world"]}
        centroids = compute_centroids(examples, fake_encode)
        assert centroids[(tenant, "question")] == pytest.approx(
            fake_encode(["hello world"])[0].tolist()
        )
