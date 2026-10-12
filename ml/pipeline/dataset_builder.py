"""S8.1: Dataset Builder & Curation.

Dagster-based pipeline for:
- Raw conversations → labeled dataset → golden set curation
- Label precedence, deduplication, PII scrubbing
- Class balance enforcement, train/test split with stratification
- Golden set tagging for high-confidence, diverse, edge-case examples
"""

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar

import numpy as np

# Optional Dagster imports - fallback to None if not available
try:
    from dagster import DynamicOut, DynamicOutput, asset, graph, job, op
    DAGSTER_AVAILABLE = True
except ImportError:
    DAGSTER_AVAILABLE = False
    # Create mock decorators for when Dagster is not available
    def asset(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if args and callable(args[0]) else decorator

    def op(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if args and callable(args[0]) else decorator

    def job(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if args and callable(args[0]) else decorator

    def graph(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if args and callable(args[0]) else decorator

    class DynamicOut:
        pass

    class DynamicOutput:
        pass

logger = logging.getLogger(__name__)


class LabelSource(Enum):
    """Label precedence: override > correction > auto_label."""
    OVERRIDE = 3
    CORRECTION = 2
    AUTO_LABEL = 1


@dataclass
class ConversationRecord:
    """Raw conversation with optional labels."""
    tenant_id: str
    conversation_id: str
    message: str
    intent: str | None = None
    label_source: LabelSource = LabelSource.AUTO_LABEL
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LabeledExample:
    """Labeled training example after curation."""
    tenant_id: str
    text: str
    intent: str
    tokens: list[str]
    embedding_hash: str
    pii_scrubbed: bool
    source_id: str
    is_golden: bool = False
    golden_reason: str | None = None


class PIIScrubber:
    """Basic PII scrubbing using keyword patterns."""

    PII_PATTERNS: ClassVar[dict[str, str]] = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\+?1?\d{9,15}",
        "ssn": r"\d{3}-\d{2}-\d{4}",
        "credit_card": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "ip_address": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    }

    @staticmethod
    def scrub(text: str) -> tuple[str, bool]:
        """Scrub PII from text. Returns (scrubbed_text, was_scrubbed)."""
        scrubbed = text
        found_pii = False

        import re
        for pii_type, pattern in PIIScrubber.PII_PATTERNS.items():
            if re.search(pattern, scrubbed):
                found_pii = True
                scrubbed = re.sub(pattern, f"[{pii_type.upper()}]", scrubbed)

        return scrubbed, found_pii


class Deduplicator:
    """Deduplication based on tenant, intent, message tokens."""

    @staticmethod
    def compute_hash(tenant_id: str, intent: str, tokens: list[str]) -> str:
        """Compute dedup hash from tenant, intent, and normalized tokens."""
        normalized = " ".join(sorted(set(tokens)))
        content = f"{tenant_id}:{intent}:{normalized}"
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def deduplicate(records: list[LabeledExample]) -> list[LabeledExample]:
        """Remove exact duplicates keeping first occurrence."""
        seen = set()
        unique = []
        for record in records:
            if record.embedding_hash not in seen:
                seen.add(record.embedding_hash)
                unique.append(record)
        return unique


class ClassBalancer:
    """Enforce minimum examples per intent class."""

    MIN_EXAMPLES_PER_CLASS = 20

    @staticmethod
    def get_class_distribution(
        records: list[LabeledExample],
    ) -> dict[str, int]:
        """Count examples per intent."""
        dist = defaultdict(int)
        for record in records:
            dist[record.intent] += 1
        return dict(dist)

    @staticmethod
    def balance_classes(
        records: list[LabeledExample],
        min_per_class: int = MIN_EXAMPLES_PER_CLASS,
    ) -> list[LabeledExample]:
        """Filter classes with < min_per_class examples."""
        dist = ClassBalancer.get_class_distribution(records)
        valid_classes = {
            intent for intent, count in dist.items()
            if count >= min_per_class
        }
        return [r for r in records if r.intent in valid_classes]


class TrainTestSplitter:
    """Stratified train/test split by intent and tenant."""

    @staticmethod
    def stratified_split(
        records: list[LabeledExample],
        test_ratio: float = 0.2,
        random_state: int = 42,
    ) -> tuple[list[LabeledExample], list[LabeledExample]]:
        """Perform stratified split preserving intent distribution per tenant."""
        np.random.seed(random_state)

        # Group by tenant and intent
        groups = defaultdict(list)
        for record in records:
            key = (record.tenant_id, record.intent)
            groups[key].append(record)

        train, test = [], []
        for group in groups.values():
            # Shuffle within group
            np.random.shuffle(group)
            split_idx = max(1, int(len(group) * (1 - test_ratio)))
            train.extend(group[:split_idx])
            test.extend(group[split_idx:])

        return train, test


class GoldenSetTagger:
    """Tag golden set: high-confidence, diverse, edge-cases."""

    @staticmethod
    def score_confidence(
        record: LabeledExample,
        label_source_priority: dict,
    ) -> float:
        """Confidence based on label source."""
        return label_source_priority.get(record.label_source, 0.0)

    @staticmethod
    def score_diversity(
        record: LabeledExample,
        all_records: list[LabeledExample],
    ) -> float:
        """Diversity: rarity of (intent, token_subset) pair."""
        subset = set(record.tokens[:5])
        similar_count = sum(
            1 for r in all_records
            if r.intent == record.intent and set(r.tokens[:5]) & subset
        )
        return 1.0 / (1.0 + similar_count / len(all_records))

    @staticmethod
    def score_edge_case(record: LabeledExample) -> float:
        """Edge case: unusual token patterns, length outliers."""
        is_short = len(record.tokens) < 3
        is_long = len(record.tokens) > 50
        has_special = any(t.startswith("[") for t in record.tokens)
        edge_score = sum([is_short, is_long, has_special]) / 3.0
        return edge_score

    @staticmethod
    def tag_golden_set(
        records: list[LabeledExample],
        target_count: int = 500,
        confidence_weight: float = 0.4,
        diversity_weight: float = 0.3,
        edge_case_weight: float = 0.3,
    ) -> list[LabeledExample]:
        """Select golden set by weighted score."""
        label_priority = {
            LabelSource.OVERRIDE: 1.0,
            LabelSource.CORRECTION: 0.8,
            LabelSource.AUTO_LABEL: 0.5,
        }

        tagged = []
        for record in records:
            conf_score = GoldenSetTagger.score_confidence(record, label_priority)
            div_score = GoldenSetTagger.score_diversity(record, records)
            edge_score = GoldenSetTagger.score_edge_case(record)

            combined_score = (
                confidence_weight * conf_score +
                diversity_weight * div_score +
                edge_case_weight * edge_score
            )

            reason = None
            if conf_score > 0.8:
                reason = "high_confidence"
            elif div_score > 0.7:
                reason = "diverse"
            elif edge_score > 0.6:
                reason = "edge_case"

            record.is_golden = combined_score > 0.6
            record.golden_reason = reason
            tagged.append(record)

        # Sort by score and take top target_count
        tagged_sorted = sorted(
            tagged,
            key=lambda r: (r.is_golden, r.golden_reason is not None),
            reverse=True
        )

        for record in tagged_sorted[:target_count]:
            record.is_golden = True

        return tagged_sorted


# Dagster ops
@op
def load_raw_conversations(data_dir: str) -> list[ConversationRecord]:
    """Load raw conversations from jsonl."""
    records = []
    path = Path(data_dir)
    if not path.exists():
        logger.warning(f"Data dir {data_dir} not found, returning empty")
        return []

    for file in path.glob("*.jsonl"):
        with open(file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    records.append(
                        ConversationRecord(
                            tenant_id=data.get("tenant_id", "default"),
                            conversation_id=data.get("id", ""),
                            message=data.get("message", ""),
                            intent=data.get("intent"),
                            label_source=LabelSource[data.get("label_source", "AUTO_LABEL")],
                            metadata=data.get("metadata", {}),
                        )
                    )
                except Exception as e:
                    logger.error(f"Error parsing line in {file}: {e}")

    return records


@op
def apply_label_precedence(
    records: list[ConversationRecord],
) -> list[ConversationRecord]:
    """Apply label precedence: override > correction > auto_label."""
    result = []
    by_id = defaultdict(list)

    for record in records:
        by_id[record.conversation_id].append(record)

    for conv_records in by_id.values():
        # Sort by precedence
        sorted_records = sorted(
            conv_records,
            key=lambda r: r.label_source.value,
            reverse=True
        )
        result.append(sorted_records[0])

    return result


@op
def scrub_pii(records: list[ConversationRecord]) -> list[ConversationRecord]:
    """Scrub PII from all message text."""
    for record in records:
        scrubbed, _ = PIIScrubber.scrub(record.message)
        record.message = scrubbed
    return records


@op
def tokenize_and_deduplicate(
    records: list[ConversationRecord],
) -> list[LabeledExample]:
    """Tokenize, compute dedup hash, and deduplicate."""
    labeled = []

    for record in records:
        if not record.intent:
            continue

        # Simple tokenization
        tokens = record.message.lower().split()
        tokens = [t.strip('.,!?;:') for t in tokens if t.strip()]

        dedup_hash = Deduplicator.compute_hash(
            record.tenant_id,
            record.intent,
            tokens,
        )

        labeled.append(
            LabeledExample(
                tenant_id=record.tenant_id,
                text=record.message,
                intent=record.intent,
                tokens=tokens,
                embedding_hash=dedup_hash,
                pii_scrubbed=True,
                source_id=record.conversation_id,
            )
        )

    # Deduplicate
    unique = Deduplicator.deduplicate(labeled)
    logger.info(f"Deduplicated {len(labeled)} → {len(unique)} examples")

    return unique


@op
def balance_classes(examples: list[LabeledExample]) -> list[LabeledExample]:
    """Drop classes with < 20 examples."""
    before_dist = ClassBalancer.get_class_distribution(examples)
    balanced = ClassBalancer.balance_classes(examples)
    after_dist = ClassBalancer.get_class_distribution(balanced)

    logger.info(f"Class distribution before: {before_dist}")
    logger.info(f"Class distribution after: {after_dist}")

    return balanced


@op
def create_stratified_split(
    examples: list[LabeledExample],
) -> tuple[list[LabeledExample], list[LabeledExample]]:
    """Create 80/20 train/test split stratified by tenant and intent."""
    train, test = TrainTestSplitter.stratified_split(examples, test_ratio=0.2)
    logger.info(f"Train/test split: {len(train)} / {len(test)}")
    return train, test


@op
def create_golden_set(examples: list[LabeledExample]) -> list[LabeledExample]:
    """Tag golden set with high-confidence, diverse, edge-case examples."""
    golden = GoldenSetTagger.tag_golden_set(examples, target_count=500)
    golden_count = sum(1 for r in golden if r.is_golden)
    logger.info(f"Tagged {golden_count} examples as golden set")
    return golden


@asset(name="raw_conversations")
def raw_conversations_asset() -> list[ConversationRecord]:
    """Load raw conversations from data directory."""
    return load_raw_conversations("data/raw_conversations")


@asset(name="labeled_dataset", deps=["raw_conversations_asset"])
def labeled_dataset_asset() -> list[LabeledExample]:
    """Curated labeled dataset with dedup, PII scrub, class balance."""
    raw = load_raw_conversations("data/raw_conversations")
    raw = apply_label_precedence(raw)
    raw = scrub_pii(raw)
    labeled = tokenize_and_deduplicate(raw)
    balanced = balance_classes(labeled)
    return balanced


@asset(name="golden_set_curated", deps=["labeled_dataset"])
def golden_set_curated_asset() -> dict:
    """Golden set with stratified train/test and golden tags."""
    labeled = labeled_dataset_asset()
    train, test = TrainTestSplitter.stratified_split(labeled)
    golden = create_golden_set(labeled)

    return {
        "train": [r for r in train if r.is_golden],
        "test": [r for r in test if r.is_golden],
        "all_labeled": labeled,
        "all_golden": golden,
    }


@job
def dataset_curation_job():
    """Full dataset curation pipeline."""
    raw = load_raw_conversations("data/raw_conversations")
    raw = apply_label_precedence(raw)
    raw = scrub_pii(raw)
    labeled = tokenize_and_deduplicate(raw)
    balanced = balance_classes(labeled)
    train, test = create_stratified_split(balanced)
    golden = create_golden_set(balanced)
    return {"train": train, "test": test, "golden": golden}
