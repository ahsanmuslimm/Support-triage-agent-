"""Shared pytest configuration and fixtures."""

import asyncio
import os

import pytest


# Configure pytest-asyncio mode
def pytest_configure(config):  # type: ignore
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def clear_tenant_context():
    """Clear tenant context before each test."""
    from py_core.tenant import clear_tenant
    clear_tenant()
    yield
    clear_tenant()
