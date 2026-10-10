"""Unit tests for tenant context management."""

import asyncio
from uuid import UUID, uuid4

import pytest

from py_core.tenant import (
    MissingTenantContextError,
    clear_tenant,
    get_tenant,
    set_tenant,
)


@pytest.mark.unit
def test_get_tenant_not_set_raises_error() -> None:
    """Test that getting tenant when not set raises MissingTenantContextError."""
    clear_tenant()  # Ensure clean state
    with pytest.raises(MissingTenantContextError):
        get_tenant()


@pytest.mark.unit
def test_set_and_get_tenant() -> None:
    """Test setting and retrieving tenant ID."""
    tenant_id = uuid4()
    set_tenant(tenant_id)
    assert get_tenant() == tenant_id


@pytest.mark.unit
async def test_tenant_isolation_across_coroutines() -> None:
    """Test that tenant context is isolated across async tasks."""

    async def task_with_tenant(tenant_id: UUID) -> UUID:
        set_tenant(tenant_id)
        await asyncio.sleep(0.001)  # Simulate async work
        return get_tenant()

    tenant_1 = uuid4()
    tenant_2 = uuid4()

    # Run tasks concurrently
    results = await asyncio.gather(
        task_with_tenant(tenant_1),
        task_with_tenant(tenant_2),
    )

    assert results[0] == tenant_1
    assert results[1] == tenant_2


@pytest.mark.unit
def test_clear_tenant() -> None:
    """Test clearing tenant context."""
    tenant_id = uuid4()
    set_tenant(tenant_id)
    assert get_tenant() == tenant_id

    clear_tenant()
    with pytest.raises(MissingTenantContextError):
        get_tenant()
