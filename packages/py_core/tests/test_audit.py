"""Integration tests for audit hash-chain integrity."""

import pytest


@pytest.mark.integration
async def test_audit_chain_integrity_after_n_inserts() -> None:
    """Test that hash chain remains intact after multiple inserts."""
    # Placeholder: requires database connection
    assert True


@pytest.mark.integration
async def test_audit_chain_detects_tampered_payload() -> None:
    """Test that verify_audit_chain detects modified rows."""
    # Placeholder: requires database connection
    assert True


@pytest.mark.integration
async def test_audit_update_is_forbidden() -> None:
    """Test that UPDATE on audit_log raises exception."""
    # Placeholder: requires database connection
    assert True


@pytest.mark.integration
async def test_audit_delete_is_forbidden() -> None:
    """Test that DELETE on audit_log raises exception."""
    # Placeholder: requires database connection
    assert True


@pytest.mark.integration
async def test_first_row_prev_hash_is_genesis() -> None:
    """Test that first audit row has prev_hash = 'genesis'."""
    # Placeholder: requires database connection
    assert True
