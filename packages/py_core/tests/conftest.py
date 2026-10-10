"""Shared pytest configuration and fixtures."""

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


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


@pytest_asyncio.fixture(scope="session")
async def pg_engine():
    """Create PostgreSQL engine for integration tests.
    
    Uses testcontainers to spin up a temporary Postgres database.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    
    # Start PostgreSQL container
    container = PostgresContainer("postgres:18-alpine")
    container.start()
    
    # Create async engine
    connection_string = f"postgresql+asyncpg://{container.username}:{container.password}@{container.get_container_host_ip()}:{container.get_exposed_port(5432)}/{container.dbname}"
    engine = create_async_engine(connection_string, echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        # Create pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        
        # Import models and create schema
        from alembic.config import Config as AlembicConfig
        from alembic import command
        from sqlalchemy import text
        
        # For simplicity, create schema manually via SQL
        # (Alembic setup would require more configuration)
        schema_setup = """
        -- Schema and types already handled by migrations
        -- For now, we'll use raw SQL to setup minimal tables for tests
        """
    
    yield engine
    
    # Stop container
    container.stop()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Create a database session for each test."""
    async_session_maker = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        # For integration tests, ensure schema exists
        async with pg_engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgvector")
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        
        yield session
        await session.rollback()
