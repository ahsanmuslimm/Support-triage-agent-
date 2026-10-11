"""ML-based entity extraction using HuggingFace NER models."""

from typing import List, Optional
import structlog

from triage.models.entity import ExtractedEntity, EntityType, EntityExtractionResult

log = structlog.get_logger()

# Lazy-load transformer to avoid startup penalty
_ner_pipeline = None


def get_ner_pipeline():
    """Load NER pipeline lazily."""
    global _ner_pipeline
    if _ner_pipeline is None:
        try:
            from transformers import pipeline
            _ner_pipeline = pipeline(
                "ner",
                model="dslim/bert-base-multilingual-cased-ner-hrl",
                aggregation_strategy="simple"
            )
            log.info("ml_extractor_loaded", model="dslim/bert-base-multilingual-cased-ner-hrl")
        except Exception as e:
            log.warning("ml_extractor_unavailable", error=str(e))
            return None
    return _ner_pipeline


class MLEntityExtractor:
    """Extract entities using HuggingFace NER model with confidence scores."""

    # Map HF NER tags to custom entity types
    TAG_MAPPING = {
        "PER": EntityType.PRODUCT,  # Placeholder for custom mapping
        "ORG": EntityType.PRODUCT,
        "LOC": EntityType.PRODUCT,
    }

    def __init__(self):
        """Initialize ML extractor."""
        self.pipeline = get_ner_pipeline()
        self.available = self.pipeline is not None

    def extract(self, text: str, message_id: str) -> EntityExtractionResult:
        """Extract entities using HuggingFace NER.

        Args:
            text: Message text to extract from
            message_id: ID of the message being processed

        Returns:
            EntityExtractionResult with extracted entities
        """
        entities: List[ExtractedEntity] = []
        errors: List[str] = []

        if not self.available:
            log.debug("ml_extractor_unavailable_fallback", message_id=message_id)
            return EntityExtractionResult(
                message_id=message_id,
                entities=entities,
                redacted_text=text,
                extraction_errors=["ML extractor not available; using fallback"],
            )

        try:
            # Run NER on text
            ner_results = self.pipeline(text[:512])  # Limit to 512 chars for performance

            for result in ner_results:
                # Map NER tag to EntityType
                entity_type = self._map_tag_to_entity_type(result.get("entity_group", ""))
                if not entity_type:
                    continue

                value = result.get("word", "").strip()
                if not value:
                    continue

                confidence = result.get("score", 0.0)

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=value,
                    normalized_value=value,
                    confidence=confidence,
                    start_pos=result.get("start", None),
                    end_pos=result.get("end", None),
                    is_pii=False,  # ML extractor doesn't flag PII yet
                )
                entities.append(entity)

        except Exception as e:
            log.error("ml_extraction_error", message_id=message_id, error=str(e))
            errors.append(f"ML extraction failed: {str(e)}")

        return EntityExtractionResult(
            message_id=message_id,
            entities=entities,
            redacted_text=text,
            extraction_errors=errors,
        )

    @staticmethod
    def _map_tag_to_entity_type(tag: str) -> Optional[EntityType]:
        """Map HF NER tag to custom entity type.

        For now, most tags map to PRODUCT placeholder.
        Later can be enhanced with fine-tuning.
        """
        # In a real system, fine-tune model to produce custom labels
        # For now, simple mapping
        tag_lower = tag.lower()
        if "product" in tag_lower or "item" in tag_lower:
            return EntityType.PRODUCT
        elif "person" in tag_lower or "per" in tag_lower:
            return None  # Skip person names for now
        elif "org" in tag_lower:
            return None  # Skip organizations
        return None  # Default: skip unknown tags

    def is_available(self) -> bool:
        """Check if ML extractor is available."""
        return self.available
