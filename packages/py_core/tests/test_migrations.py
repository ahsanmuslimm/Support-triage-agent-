"""Integration tests for database migrations."""

import pytest
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_migration_baseline_schema_created(pg_session: AsyncSession) -> None:
    """Test that baseline migration creates all tables."""
    expected_tables = [
        "tenants", "customers", "channels", "intents", "intent_examples",
        "autonomy_settings", "conversations", "messages", "triage_runs",
        "predictions", "entities", "response_drafts", "handoff_packets",
        "kb_sources", "kb_documents", "kb_chunks", "action_definitions",
        "action_executions", "assignments", "feedback", "outbox_events",
        "audit_log", "pii_tokens"
    ]
    
    # Get list of tables in triage schema
    result = await pg_session.execute(
        text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'triage'
        """)
    )
    
    existing_tables = {row[0] for row in result.fetchall()}
    
    # Verify all expected tables exist
    for table_name in expected_tables:
        assert table_name in existing_tables, f"Table '{table_name}' not found in triage schema"


@pytest.mark.integration
async def test_rls_enabled_on_tenant_tables(pg_session: AsyncSession) -> None:
    """Test that Row-Level Security is enabled on multi-tenant tables."""
    multi_tenant_tables = [
        "customers", "channels", "intents", "intent_examples",
        "autonomy_settings", "conversations", "messages", "triage_runs",
        "predictions", "entities", "response_drafts", "handoff_packets",
        "kb_sources", "kb_documents", "kb_chunks", "action_definitions",
        "action_executions", "assignments", "feedback", "outbox_events",
        "audit_log", "pii_tokens"
    ]
    
    for table_name in multi_tenant_tables:
        result = await pg_session.execute(
            text("""
                SELECT relrowsecurity FROM pg_class 
                WHERE relname = :table_name 
                AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'triage')
            """),
            {"table_name": table_name}
        )
        
        rls_enabled = result.scalar()
        assert rls_enabled is True, f"RLS not enabled on table '{table_name}'"


@pytest.mark.integration
async def test_rls_policy_blocks_cross_tenant_read(pg_session: AsyncSession) -> None:
    """Test that RLS policies enforce tenant isolation."""
    from uuid import uuid4
    
    tenant_a = uuid4()
    tenant_b = uuid4()
    
    # Create tenants
    await pg_session.execute(
        text("""
            INSERT INTO triage.tenants (id, slug, name, config)
            VALUES (:id, :slug, :name, '{}')
        """),
        {"id": tenant_a, "slug": f"tenant-a", "name": "Tenant A"}
    )
    
    await pg_session.execute(
        text("""
            INSERT INTO triage.tenants (id, slug, name, config)
            VALUES (:id, :slug, :name, '{}')
        """),
        {"id": tenant_b, "slug": f"tenant-b", "name": "Tenant B"}
    )
    
    # Insert customer for tenant A
    customer_a_id = uuid4()
    await pg_session.execute(
        text("""
            INSERT INTO triage.customers (tenant_id, id, email_hash)
            VALUES (:tenant_id, :id, :email_hash)
        """),
        {
            "tenant_id": tenant_a,
            "id": customer_a_id,
            "email_hash": "hash_a@example.com"
        }
    )
    
    await pg_session.commit()
    
    # Now set context to tenant B and try to read tenant A's data
    await pg_session.execute(
        text("SET app.tenant_id = :tenant_id"),
        {"tenant_id": tenant_b}
    )
    
    result = await pg_session.execute(
        text("""
            SELECT COUNT(*) FROM triage.customers WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_a}
    )
    
    count = result.scalar()
    
    # Tenant B should not see tenant A's data due to RLS
    assert count == 0, "RLS policy should prevent cross-tenant reads"
