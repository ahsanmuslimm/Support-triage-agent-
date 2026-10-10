"""Tenant context management for multi-tenant isolation."""

from contextvars import ContextVar
from typing import Optional
from uuid import UUID

# Context var for the current tenant ID
_current_tenant_id: ContextVar[Optional[UUID]] = ContextVar(
    "_current_tenant_id", default=None
)


class MissingTenantContextError(RuntimeError):
    """Raised when tenant context is required but not set."""

    def __init__(self) -> None:
        super().__init__(
            "Missing tenant context. Call set_tenant(tenant_id) before accessing tenant-scoped resources."
        )


def set_tenant(tenant_id: UUID) -> None:
    """Set the current tenant ID in the context.

    Args:
        tenant_id: UUID of the tenant to set as current.
    """
    _current_tenant_id.set(tenant_id)


def get_tenant() -> UUID:
    """Get the current tenant ID from the context.

    Returns:
        UUID: The current tenant ID.

    Raises:
        MissingTenantContextError: If tenant context has not been set.
    """
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise MissingTenantContextError()
    return tenant_id


def clear_tenant() -> None:
    """Clear the current tenant context."""
    _current_tenant_id.set(None)
