"""Entity validation for cross-tenant isolation and tool binding."""

import structlog
from typing import Tuple, Optional

from triage.models.entity import ExtractedEntity, EntityValidationResult

log = structlog.get_logger()


class EntityValidator:
    """Validates extracted entities for safe tool binding."""

    MIN_CONFIDENCE_FOR_BINDING = 0.8
    """Minimum confidence to bind entity to tool."""

    def __init__(self, tenant_id: str, customer_id: str):
        """Initialize validator for specific tenant and customer.

        Args:
            tenant_id: Current tenant ID.
            customer_id: Current customer ID.
        """
        self.tenant_id = tenant_id
        self.customer_id = customer_id

    def validate_for_tool(
        self,
        entity: ExtractedEntity,
        linked_tenant_id: Optional[str] = None,
    ) -> EntityValidationResult:
        """Validate entity is safe to pass to tool executor.

        Args:
            entity: Entity to validate.
            linked_tenant_id: Tenant ID of the linked resource (e.g., order's tenant).
                             If None, assumes current tenant.

        Returns:
            EntityValidationResult with validation status.
        """
        entity_id = f"{entity.entity_type}_{entity.value}"

        # Check 1: Confidence >= threshold
        if entity.confidence < self.MIN_CONFIDENCE_FOR_BINDING:
            return EntityValidationResult(
                entity_id=entity_id,
                valid=False,
                reason=f"Confidence {entity.confidence:.2f} < {self.MIN_CONFIDENCE_FOR_BINDING}",
                can_bind_to_tool=False,
                cross_tenant_risk=False,
            )

        # Check 2: Entity must be linked (verified in DB)
        if entity.linked_id is None:
            return EntityValidationResult(
                entity_id=entity_id,
                valid=False,
                reason=f"Entity {entity.entity_type}={entity.value} not linked to DB record",
                can_bind_to_tool=False,
                cross_tenant_risk=False,
            )

        # Check 3: Cross-tenant isolation
        # Linked resource must belong to current tenant
        resource_tenant = linked_tenant_id or self.tenant_id
        if resource_tenant != self.tenant_id:
            log.error(
                "cross_tenant_risk_detected",
                entity=entity_id,
                customer_id=self.customer_id,
                resource_tenant=resource_tenant,
                current_tenant=self.tenant_id,
            )
            return EntityValidationResult(
                entity_id=entity_id,
                valid=False,
                reason=f"Cross-tenant leak detected: entity links to tenant {resource_tenant}, current tenant {self.tenant_id}",
                can_bind_to_tool=False,
                cross_tenant_risk=True,
            )

        # Check 4: Amount validation (if applicable)
        if entity.entity_type.name == "AMOUNT":
            try:
                amount = float(entity.value.replace("$", "").replace(",", ""))
                if amount < 0:
                    return EntityValidationResult(
                        entity_id=entity_id,
                        valid=False,
                        reason=f"Amount is negative: ${amount}",
                        can_bind_to_tool=False,
                        cross_tenant_risk=False,
                    )
                if amount > 1_000_000:
                    return EntityValidationResult(
                        entity_id=entity_id,
                        valid=False,
                        reason=f"Amount exceeds limit: ${amount} > $1,000,000",
                        can_bind_to_tool=False,
                        cross_tenant_risk=False,
                    )
            except (ValueError, AttributeError):
                return EntityValidationResult(
                    entity_id=entity_id,
                    valid=False,
                    reason=f"Invalid amount format: {entity.value}",
                    can_bind_to_tool=False,
                    cross_tenant_risk=False,
                )

        # All checks passed
        log.info(
            "entity_validated",
            entity_id=entity_id,
            confidence=entity.confidence,
            linked_id=entity.linked_id,
        )

        return EntityValidationResult(
            entity_id=entity_id,
            valid=True,
            reason=f"Entity verified: confidence {entity.confidence:.2f}, linked_id {entity.linked_id}",
            can_bind_to_tool=True,
            cross_tenant_risk=False,
        )

    def validate_entities_batch(
        self,
        entities: list[ExtractedEntity],
        linked_tenant_ids: Optional[dict[str, str]] = None,
    ) -> list[EntityValidationResult]:
        """Validate multiple entities.

        Args:
            entities: List of entities to validate.
            linked_tenant_ids: Dict mapping entity_type -> tenant_id for cross-tenant check.

        Returns:
            List of validation results.
        """
        linked_tenant_ids = linked_tenant_ids or {}
        return [
            self.validate_for_tool(entity, linked_tenant_ids.get(entity.entity_type.name))
            for entity in entities
        ]
