"""Entity linking: resolve extracted entities to database records."""

from typing import Optional, Dict, Any
import structlog
from enum import Enum

from triage.models.entity import ExtractedEntity, EntityType

log = structlog.get_logger()


class LinkResult:
    """Result of linking an entity to a database record."""

    def __init__(
        self,
        entity_type: EntityType,
        value: str,
        linked_id: Optional[int] = None,
        linked_data: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.entity_type = entity_type
        self.value = value
        self.linked_id = linked_id
        self.linked_data = linked_data or {}
        self.tenant_id = tenant_id
        self.error = error

    @property
    def success(self) -> bool:
        return self.linked_id is not None and self.error is None


class EntityLinker:
    """Link extracted entities to database records for verification."""

    def __init__(self, tenant_id: str):
        """Initialize linker for a specific tenant.

        Args:
            tenant_id: Current tenant ID (for cross-tenant isolation)
        """
        self.tenant_id = tenant_id

    async def link(self, entity: ExtractedEntity) -> LinkResult:
        """Link an entity to a database record.

        Args:
            entity: Entity to link

        Returns:
            LinkResult with linked_id and tenant verification
        """
        try:
            if entity.entity_type == EntityType.ORDER_ID:
                return await self._link_order(entity)
            elif entity.entity_type == EntityType.EMAIL:
                return await self._link_customer_by_email(entity)
            elif entity.entity_type == EntityType.PHONE:
                return await self._link_customer_by_phone(entity)
            elif entity.entity_type == EntityType.ACCOUNT_ID:
                return await self._link_account(entity)
            else:
                return LinkResult(
                    entity_type=entity.entity_type,
                    value=entity.value,
                    error="Entity type not linkable",
                )
        except Exception as e:
            log.error(
                "entity_linking_error",
                entity_type=entity.entity_type,
                value=entity.value,
                error=str(e),
            )
            return LinkResult(
                entity_type=entity.entity_type,
                value=entity.value,
                error=f"Linking failed: {str(e)}",
            )

    async def _link_order(self, entity: ExtractedEntity) -> LinkResult:
        """Link ORDER_ID to database order record.

        In production: query triage.orders table.
        For now: mock implementation.
        """
        # TODO: Query database for order
        # SELECT id, tenant_id FROM orders WHERE order_id = ?
        # Verify tenant_id matches current tenant

        # Mock: accept any order ID with 6+ digits
        normalized = entity.normalized_value or entity.value
        try:
            order_id_num = int("".join(c for c in normalized if c.isdigit()))
            if order_id_num > 0:
                return LinkResult(
                    entity_type=EntityType.ORDER_ID,
                    value=entity.value,
                    linked_id=order_id_num,
                    linked_data={"order_number": entity.value},
                    tenant_id=self.tenant_id,
                )
        except ValueError:
            pass

        return LinkResult(
            entity_type=EntityType.ORDER_ID,
            value=entity.value,
            error="Order not found in database",
        )

    async def _link_customer_by_email(self, entity: ExtractedEntity) -> LinkResult:
        """Link EMAIL to customer record."""
        # TODO: Query database for customer
        # SELECT id, tenant_id FROM customers WHERE email = ?

        # Mock: accept any valid email
        if "@" in entity.value:
            return LinkResult(
                entity_type=EntityType.EMAIL,
                value=entity.value,
                linked_id=hash(entity.value) % 1000000,  # Fake customer ID
                linked_data={"email": entity.value},
                tenant_id=self.tenant_id,
            )

        return LinkResult(
            entity_type=EntityType.EMAIL,
            value=entity.value,
            error="Customer not found by email",
        )

    async def _link_customer_by_phone(self, entity: ExtractedEntity) -> LinkResult:
        """Link PHONE to customer record."""
        # TODO: Query database for customer
        # SELECT id, tenant_id FROM customers WHERE phone = ?

        # Mock: accept any phone
        if entity.value:
            return LinkResult(
                entity_type=EntityType.PHONE,
                value=entity.value,
                linked_id=hash(entity.value) % 1000000,
                linked_data={"phone": entity.value},
                tenant_id=self.tenant_id,
            )

        return LinkResult(
            entity_type=EntityType.PHONE,
            value=entity.value,
            error="Customer not found by phone",
        )

    async def _link_account(self, entity: ExtractedEntity) -> LinkResult:
        """Link ACCOUNT_ID to account record."""
        # TODO: Query database for account
        # SELECT id, tenant_id FROM accounts WHERE account_id = ?

        # Mock
        try:
            account_id = int("".join(c for c in entity.value if c.isdigit()))
            if account_id > 0:
                return LinkResult(
                    entity_type=EntityType.ACCOUNT_ID,
                    value=entity.value,
                    linked_id=account_id,
                    linked_data={"account_id": entity.value},
                    tenant_id=self.tenant_id,
                )
        except ValueError:
            pass

        return LinkResult(
            entity_type=EntityType.ACCOUNT_ID,
            value=entity.value,
            error="Account not found",
        )
