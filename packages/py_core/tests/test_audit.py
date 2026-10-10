"""Integration tests for audit hash-chain integrity."""

import pytest
import json
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_audit_chain_integrity_after_n_inserts(pg_session: AsyncSession) -> None:
    """Test that hash chain remains intact after multiple inserts."""
    tenant_id = uuid4()
    actor_id = uuid4()
    
    # Insert 5 audit records
    for i in range(5):
        await pg_session.execute(
            text("""
                INSERT INTO triage.audit_log 
                (tenant_id, actor_id, actor_type, action, target_type, target_id, payload, prev_hash, row_hash)
                VALUES (:tenant_id, :actor_id, :actor_type, :action, :target_type, :target_id, :payload, '', '')
            """),
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_type": "user",
                "action": "create",
                "target_type": "conversation",
                "target_id": uuid4(),
                "payload": json.dumps({"test": f"insert_{i}"})
            }
        )
    
    await pg_session.commit()
    
    # Verify chain integrity
    result = await pg_session.execute(
        text("""
            SELECT verify_audit_chain(:tenant_id)
        """),
        {"tenant_id": tenant_id}
    )
    broken_rows = result.scalars().all()
    
    # Chain should be intact (no broken links)
    assert len(broken_rows) == 0, "Audit chain should be intact after inserts"


@pytest.mark.integration
async def test_audit_chain_detects_tampered_payload(pg_session: AsyncSession) -> None:
    """Test that verify_audit_chain detects modified rows."""
    tenant_id = uuid4()
    actor_id = uuid4()
    
    # Insert one record
    await pg_session.execute(
        text("""
            INSERT INTO triage.audit_log 
            (tenant_id, actor_id, actor_type, action, target_type, target_id, payload, prev_hash, row_hash)
            VALUES (:tenant_id, :actor_id, :actor_type, :action, :target_type, :target_id, :payload, '', '')
        """),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_type": "user",
            "action": "create",
            "target_type": "conversation",
            "target_id": uuid4(),
            "payload": json.dumps({"test": "original"})
        }
    )
    
    await pg_session.commit()
    
    # Get the row ID
    row_result = await pg_session.execute(
        text("SELECT id FROM triage.audit_log WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id}
    )
    row_id = row_result.scalar()
    
    # Tamper with the payload (using raw SQL bypass)
    await pg_session.execute(
        text("""
            UPDATE triage.audit_log 
            SET payload = :new_payload 
            WHERE id = :row_id
        """),
        {
            "row_id": row_id,
            "new_payload": json.dumps({"test": "tampered"})
        }
    )
    
    await pg_session.commit()
    
    # Verify chain - should detect tampering
    result = await pg_session.execute(
        text("""
            SELECT verify_audit_chain(:tenant_id)
        """),
        {"tenant_id": tenant_id}
    )
    broken_rows = result.scalars().all()
    
    # Should detect the tampered row
    assert len(broken_rows) > 0, "Audit chain verification should detect tampering"


@pytest.mark.integration
async def test_audit_update_is_forbidden(pg_session: AsyncSession) -> None:
    """Test that UPDATE on audit_log raises exception."""
    tenant_id = uuid4()
    actor_id = uuid4()
    
    # Insert one record
    await pg_session.execute(
        text("""
            INSERT INTO triage.audit_log 
            (tenant_id, actor_id, actor_type, action, target_type, target_id, payload, prev_hash, row_hash)
            VALUES (:tenant_id, :actor_id, :actor_type, :action, :target_type, :target_id, :payload, '', '')
        """),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_type": "user",
            "action": "create",
            "target_type": "conversation",
            "target_id": uuid4(),
            "payload": json.dumps({"test": "original"})
        }
    )
    
    await pg_session.commit()
    
    # Attempt UPDATE should raise exception
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text("""
                UPDATE triage.audit_log 
                SET action = 'update' 
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id}
        )
        await pg_session.commit()
    
    # Should contain 'append-only' in the error
    assert "append-only" in str(exc_info.value).lower() or "update" in str(exc_info.value).lower()


@pytest.mark.integration
async def test_audit_delete_is_forbidden(pg_session: AsyncSession) -> None:
    """Test that DELETE on audit_log raises exception."""
    tenant_id = uuid4()
    actor_id = uuid4()
    
    # Insert one record
    await pg_session.execute(
        text("""
            INSERT INTO triage.audit_log 
            (tenant_id, actor_id, actor_type, action, target_type, target_id, payload, prev_hash, row_hash)
            VALUES (:tenant_id, :actor_id, :actor_type, :action, :target_type, :target_id, :payload, '', '')
        """),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_type": "user",
            "action": "create",
            "target_type": "conversation",
            "target_id": uuid4(),
            "payload": json.dumps({"test": "original"})
        }
    )
    
    await pg_session.commit()
    
    # Attempt DELETE should raise exception
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text("""
                DELETE FROM triage.audit_log 
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id}
        )
        await pg_session.commit()
    
    # Should contain 'append-only' in the error
    assert "append-only" in str(exc_info.value).lower() or "delete" in str(exc_info.value).lower()


@pytest.mark.integration
async def test_first_row_prev_hash_is_genesis(pg_session: AsyncSession) -> None:
    """Test that first audit row has prev_hash = 'genesis'."""
    tenant_id = uuid4()
    actor_id = uuid4()
    
    # Insert one record (should be first for this tenant)
    await pg_session.execute(
        text("""
            INSERT INTO triage.audit_log 
            (tenant_id, actor_id, actor_type, action, target_type, target_id, payload, prev_hash, row_hash)
            VALUES (:tenant_id, :actor_id, :actor_type, :action, :target_type, :target_id, :payload, '', '')
        """),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_type": "user",
            "action": "create",
            "target_type": "conversation",
            "target_id": uuid4(),
            "payload": json.dumps({"test": "first"})
        }
    )
    
    await pg_session.commit()
    
    # Query the row
    result = await pg_session.execute(
        text("""
            SELECT prev_hash FROM triage.audit_log 
            WHERE tenant_id = :tenant_id 
            ORDER BY id ASC 
            LIMIT 1
        """),
        {"tenant_id": tenant_id}
    )
    prev_hash = result.scalar()
    
    # First row should have prev_hash = 'genesis'
    assert prev_hash == "genesis", f"First audit row should have prev_hash='genesis', got '{prev_hash}'"
