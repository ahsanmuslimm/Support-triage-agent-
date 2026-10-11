"""Rule-based entity extraction using regex patterns."""

import re
import asyncio
from typing import List, Optional
import structlog

from triage.models.entity import ExtractedEntity, EntityType, EntityExtractionResult

log = structlog.get_logger()


class RuleBasedEntityExtractor:
    """Extract entities using regex patterns with high confidence."""

    # Regex patterns for each entity type
    PATTERNS = {
        EntityType.ORDER_ID: [
            r"#(\d{6,10})",  # #123456
            r"(ORD-[\w]+)",  # ORD-ABC123
            r"order\s+([A-Z0-9-]+)",  # order ABC123
        ],
        EntityType.AMOUNT: [
            r"\$(\d+(?:\.\d{2})?)",  # $100.50 or $100
            r"(\d+(?:\.\d{2})?)\s*(?:USD|dollars?)",  # 100.50 USD
        ],
        EntityType.EMAIL: [
            r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        ],
        EntityType.PHONE: [
            r"(\+?1?\s?[-.\(]?\d{3}[-.\)]?\s?\d{3}[-.\s]?\d{4})",  # Various US formats
            r"(\+\d{1,3}\s?\d{1,14})",  # International
        ],
        EntityType.ACCOUNT_ID: [
            r"account\s+([A-Z0-9-]+)",  # account ABC-123
            r"account\s+#(\d+)",  # account #12345
        ],
        EntityType.CREDIT_CARD: [
            r"(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})",  # 4111 1111 1111 1111
        ],
        EntityType.SSN: [
            r"(\d{3}[-\s]?\d{2}[-\s]?\d{4})",  # 123-45-6789
        ],
        EntityType.PRODUCT: [
            r"product\s+([\"']?[^\"'\n,]+[\"']?)",
            r"item\s+([\"']?[^\"'\n,]+[\"']?)",
        ],
        EntityType.DATE: [
            r"(\d{4}-\d{2}-\d{2})",  # ISO 8601: 2024-01-15
            r"(\d{1,2}/\d{1,2}/\d{2,4})",  # US: 01/15/2024
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        ],
        EntityType.TRACKING_NUMBER: [
            r"track(?:ing)?\s+#?([A-Z0-9]{10,30})",
            r"(1Z[A-Z0-9]{16})",  # UPS
        ],
    }

    # PII entity types
    PII_TYPES = {EntityType.EMAIL, EntityType.PHONE, EntityType.CREDIT_CARD, EntityType.SSN}

    def __init__(self, linker=None):
        """Initialize extractor.
        
        Args:
            linker: Optional EntityLinker instance for entity linking
        """
        self.pii_vault: dict[str, str] = {}
        self.vault_counter = 0
        self.linker = linker

    async def extract_with_linking(self, text: str, message_id: str, tenant_id: str) -> EntityExtractionResult:
        """Extract entities from text and link them to database records.

        Args:
            text: Message text to extract from
            message_id: ID of the message being processed
            tenant_id: Tenant ID for cross-tenant isolation

        Returns:
            EntityExtractionResult with extracted and linked entities
        """
        result = self.extract(text, message_id)
        
        # Link entities if linker is available
        if self.linker:
            linked_entities = []
            for entity in result.entities:
                try:
                    link_result = await self.linker.link(entity)
                    if link_result.success:
                        entity.linked_id = link_result.linked_id
                        entity.linked_tenant_id = link_result.tenant_id
                except Exception as e:
                    log.warning("entity_linking_failed", entity_type=entity.entity_type, error=str(e))
                linked_entities.append(entity)
            result.entities = linked_entities
        
        return result

    def extract(self, text: str, message_id: str) -> EntityExtractionResult:
        """Extract all entities from text using regex patterns.

        Args:
            text: Message text to extract from
            message_id: ID of the message being processed

        Returns:
            EntityExtractionResult with extracted entities
        """
        entities: List[ExtractedEntity] = []
        errors: List[str] = []
        redacted_text = text

        for entity_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                try:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        value = match.group(0)
                        # Get the first capture group if it exists
                        if match.groups():
                            value = match.group(1)

                        # Normalize based on type
                        normalized = self._normalize(entity_type, value)

                        # Check if PII
                        is_pii = entity_type in self.PII_TYPES

                        # Pseudonymize if PII
                        pseudonym = None
                        if is_pii:
                            pseudonym = self._pseudonymize(entity_type, value)
                            # Redact in text
                            redacted_text = redacted_text.replace(match.group(0), pseudonym)

                        entity = ExtractedEntity(
                            entity_type=entity_type,
                            value=value,
                            normalized_value=normalized,
                            confidence=0.95,  # High confidence for regex matches
                            start_pos=match.start(),
                            end_pos=match.end(),
                            is_pii=is_pii,
                            pseudonym=pseudonym,
                        )
                        entities.append(entity)

                except Exception as e:
                    errors.append(f"Pattern match error for {entity_type}: {str(e)}")
                    log.error("pattern_match_error", entity_type=entity_type, error=str(e))

        return EntityExtractionResult(
            message_id=message_id,
            entities=entities,
            redacted_text=redacted_text,
            extraction_errors=errors,
        )

    @staticmethod
    def _normalize(entity_type: EntityType, value: str) -> str:
        """Normalize extracted value based on type."""
        if entity_type == EntityType.PHONE:
            # Normalize to E.164-like format
            digits = re.sub(r"\D", "", value)
            if len(digits) == 10:
                return f"+1{digits}"
            elif len(digits) == 11:
                return f"+{digits}"
            return f"+{digits}"
        elif entity_type == EntityType.AMOUNT:
            # Parse to float
            return value.replace("$", "").replace(",", "")
        elif entity_type == EntityType.EMAIL:
            return value.lower()
        elif entity_type == EntityType.CREDIT_CARD:
            # Keep last 4 digits only in normalized form
            digits = re.sub(r"\D", "", value)
            return f"****{digits[-4:]}"
        elif entity_type == EntityType.SSN:
            # Keep last 4 digits only
            digits = re.sub(r"\D", "", value)
            return f"***-**-{digits[-4:]}"
        return value.strip().lower()

    def _pseudonymize(self, entity_type: EntityType, value: str) -> str:
        """Replace PII with vault token."""
        if value in self.pii_vault:
            return self.pii_vault[value]

        self.vault_counter += 1
        vault_token = f"VAULT_{entity_type.name}_{self.vault_counter}"
        self.pii_vault[value] = vault_token
        return vault_token

    def get_pii_mapping(self) -> dict[str, str]:
        """Get vault mapping (for test/debug only; never expose in production)."""
        return self.pii_vault.copy()
