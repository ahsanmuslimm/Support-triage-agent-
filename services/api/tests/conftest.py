"""Pytest fixtures for API tests."""

import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from triage.api.main import create_app


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def conversation_id():
    """Test conversation ID."""
    return "conv-456"


@pytest.fixture
def customer_id():
    """Test customer ID."""
    return "cust-789"
