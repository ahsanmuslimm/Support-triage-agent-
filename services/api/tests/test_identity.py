"""Tests for identity resolution."""

import pytest
from triage.ingestion.identity import IdentityResolver, IdentityAssuranceLevel


@pytest.fixture
def resolver():
    """Create identity resolver."""
    return IdentityResolver()


def test_resolve_new_customer_by_email(resolver):
    """Test creation of new customer by email."""
    customer = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email="alice@example.com",
        display_name="Alice",
    )

    assert customer.email == "alice@example.com"
    assert customer.display_name == "Alice"
    assert customer.ial == IdentityAssuranceLevel.IAL1


def test_resolve_existing_customer_by_email(resolver):
    """Test finding existing customer by email."""
    email = "bob@example.com"

    customer1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email=email,
    )

    customer2 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email=email,
    )

    assert customer1.customer_id == customer2.customer_id


def test_resolve_by_phone(resolver):
    """Test resolution by phone number."""
    phone = "555-123-4567"

    customer1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        phone=phone,
    )

    customer2 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        phone=phone,
    )

    assert customer1.customer_id == customer2.customer_id


def test_resolve_by_zendesk_id(resolver):
    """Test resolution by Zendesk ID."""
    zendesk_id = "12345"

    customer1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        zendesk_id=zendesk_id,
    )

    customer2 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        zendesk_id=zendesk_id,
    )

    assert customer1.customer_id == customer2.customer_id


def test_merge_identities_same_customer(resolver):
    """Test that multiple identifiers resolve to same customer."""
    email = "carol@example.com"
    phone = "555-234-5678"

    customer1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email=email,
    )

    customer2 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        phone=phone,
        email=email,  # Same email, should find existing
    )

    assert customer1.customer_id == customer2.customer_id
    assert customer2.phone == phone


def test_merge_multiple_identities(resolver):
    """Test merging when multiple channels used."""
    # First message: email only
    customer1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email="dave@example.com",
    )

    # Second message: phone (now merged with email)
    customer2 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email="dave@example.com",
        phone="555-345-6789",
    )

    assert customer1.customer_id == customer2.customer_id
    assert customer2.phone == "555-345-6789"


def test_cross_tenant_isolation(resolver):
    """Test that customers don't merge across tenants."""
    email = "eve@example.com"

    customer_tenant1 = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email=email,
    )

    customer_tenant2 = resolver.resolve_or_create(
        tenant_id="tenant-2",
        email=email,
    )

    # Should create different customers for each tenant
    assert customer_tenant1.tenant_id == "tenant-1"
    assert customer_tenant2.tenant_id == "tenant-2"
    # They should be different records
    assert customer_tenant1.customer_id != customer_tenant2.customer_id


def test_customer_to_dict(resolver):
    """Test customer serialization."""
    customer = resolver.resolve_or_create(
        tenant_id="tenant-1",
        email="frank@example.com",
        phone="555-456-7890",
        display_name="Frank",
    )

    data = customer.to_dict()

    assert data["tenant_id"] == "tenant-1"
    assert data["email"] == "frank@example.com"
    assert data["phone"] == "555-456-7890"
    assert data["ial"] == "ial1"


def test_no_identifiers_creates_new(resolver):
    """Test that customer with no identifiers creates new record."""
    customer = resolver.resolve_or_create(
        tenant_id="tenant-1",
    )

    assert customer.customer_id is not None
    assert customer.email is None
    assert customer.phone is None
