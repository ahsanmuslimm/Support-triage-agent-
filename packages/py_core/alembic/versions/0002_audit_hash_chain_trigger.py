"""Add audit hash-chain trigger for immutable append-only log.

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create audit hash-chain trigger functions."""
    # Create PL/pgSQL function for hash-chain computation
    op.execute(
        """
        CREATE OR REPLACE FUNCTION triage.audit_hash_chain()
        RETURNS TRIGGER AS $$
        DECLARE
            v_prev_hash TEXT;
            v_payload_text TEXT;
        BEGIN
            -- Get previous hash for this tenant (if any)
            SELECT row_hash INTO v_prev_hash
            FROM triage.audit_log
            WHERE tenant_id = NEW.tenant_id
            ORDER BY id DESC
            LIMIT 1;

            -- If no previous row, use 'genesis'
            IF v_prev_hash IS NULL THEN
                v_prev_hash := 'genesis';
            END IF;

            -- Store previous hash
            NEW.prev_hash := v_prev_hash;

            -- Compute row hash: sha256(prev_hash || tenant_id || actor_id || action || target_id || payload || created_at)
            v_payload_text := NEW.payload::text;
            NEW.row_hash := encode(
                digest(
                    v_prev_hash || NEW.tenant_id::text || NEW.actor_id::text ||
                    NEW.action || NEW.target_id::text || v_payload_text || NEW.created_at::text,
                    'sha256'
                ),
                'hex'
            );

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Create BEFORE INSERT trigger
    op.execute(
        """
        CREATE TRIGGER audit_hash_chain_before_insert
        BEFORE INSERT ON triage.audit_log
        FOR EACH ROW
        EXECUTE FUNCTION triage.audit_hash_chain();
        """
    )

    # Create UPDATE prevention trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION triage.audit_log_prevent_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; UPDATE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER audit_log_prevent_update
        BEFORE UPDATE ON triage.audit_log
        FOR EACH ROW
        EXECUTE FUNCTION triage.audit_log_prevent_update();
        """
    )

    # Create DELETE prevention trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION triage.audit_log_prevent_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; DELETE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER audit_log_prevent_delete
        BEFORE DELETE ON triage.audit_log
        FOR EACH ROW
        EXECUTE FUNCTION triage.audit_log_prevent_delete();
        """
    )

    # Create verification function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION triage.verify_audit_chain(p_tenant_id UUID)
        RETURNS TABLE(broken_at BIGINT, expected TEXT, found TEXT) AS $$
        DECLARE
            v_row RECORD;
            v_expected_hash TEXT;
            v_prev_hash TEXT;
            v_payload_text TEXT;
        BEGIN
            v_prev_hash := 'genesis';

            FOR v_row IN
                SELECT id, prev_hash, row_hash, tenant_id, actor_id, action, target_id, payload, created_at
                FROM triage.audit_log
                WHERE tenant_id = p_tenant_id
                ORDER BY id ASC
            LOOP
                -- Compute expected hash
                v_payload_text := v_row.payload::text;
                v_expected_hash := encode(
                    digest(
                        v_prev_hash || v_row.tenant_id::text || v_row.actor_id::text ||
                        v_row.action || v_row.target_id::text || v_payload_text || v_row.created_at::text,
                        'sha256'
                    ),
                    'hex'
                );

                -- Check if expected matches found
                IF v_expected_hash != v_row.row_hash THEN
                    RETURN QUERY SELECT v_row.id, v_expected_hash, v_row.row_hash;
                END IF;

                -- Update previous hash for next iteration
                v_prev_hash := v_row.row_hash;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    """Drop audit hash-chain functions and triggers."""
    op.execute("DROP TRIGGER IF EXISTS audit_hash_chain_before_insert ON triage.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_prevent_update ON triage.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_prevent_delete ON triage.audit_log")
    op.execute("DROP FUNCTION IF EXISTS triage.audit_hash_chain()")
    op.execute("DROP FUNCTION IF EXISTS triage.audit_log_prevent_update()")
    op.execute("DROP FUNCTION IF EXISTS triage.audit_log_prevent_delete()")
    op.execute("DROP FUNCTION IF EXISTS triage.verify_audit_chain(UUID)")
