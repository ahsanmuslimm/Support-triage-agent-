"""Sprint 1: Message ingestion tables with idempotency, encryption, PII handling.

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Sprint 1 message ingestion schema.

    NOTE: messages, conversations, outbox_events, and pii_tokens are created in
    migration 0001 (canonical definitions); this migration adds their indexes,
    plus the encryption_key_versions table and RLS for it.
    """

    # Index for idempotency key (UNIQUE per tenant)
    op.create_index(
        "idx_messages_tenant_idempotency_key",
        "messages",
        ["tenant_id", "idempotency_key"],
        schema="triage",
        unique=True,
    )

    # Index for conversation messages (ordered by created_at)
    op.create_index(
        "idx_messages_tenant_conversation_created",
        "messages",
        ["tenant_id", "conversation_id", "created_at"],
        schema="triage",
    )

    # Index for customer messages (ordered by created_at)
    op.create_index(
        "idx_messages_tenant_customer_created",
        "messages",
        ["tenant_id", "customer_id", "created_at"],
        schema="triage",
    )

    # Index for provider_message_id (for deduplication)
    op.create_index(
        "idx_messages_tenant_provider_message_id",
        "messages",
        ["tenant_id", "provider_message_id"],
        schema="triage",
    )

    # Conversations indexes (S1.9; table created in 0001)

    # Index for conversation lookups (tenant + customer + status)
    op.create_index(
        "idx_conversations_tenant_customer_status",
        "conversations",
        ["tenant_id", "customer_id", "status"],
        schema="triage",
    )

    # Index for conversation last_message_at (for coalescing window)
    op.create_index(
        "idx_conversations_tenant_last_message_at",
        "conversations",
        ["tenant_id", "last_message_at"],
        schema="triage",
    )

    # Outbox events indexes (S1.7; table created in 0001)

    # Index for outbox polling (find unpublished events)
    op.create_index(
        "idx_outbox_events_unpublished",
        "outbox_events",
        ["tenant_id", "published_at"],
        postgresql_where=sa.text("published_at IS NULL"),  # Partial index: only unpublished
        schema="triage",
    )

    # Index for outbox by aggregate (for ordering guarantees)
    op.create_index(
        "idx_outbox_events_aggregate",
        "outbox_events",
        ["tenant_id", "aggregate_type", "aggregate_id", "created_at"],
        schema="triage",
    )

    # PII tokens indexes (S1.6; table created in 0001)

    # Index for PII token lookups
    op.create_index(
        "idx_pii_tokens_tenant_hash",
        "pii_tokens",
        ["tenant_id", "pii_hash"],
        schema="triage",
    )

    # Encryption key versions table (S1.6)
    # Tracks DEK (Data Encryption Key) versions for rotation
    op.create_table(
        "encryption_key_versions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),  # (tenant_id, version) = unique
        sa.Column("dek_encrypted", sa.String(1024), nullable=False),  # Fernet-encrypted DEK (encrypted by KEK)
        sa.Column("algorithm", sa.String(50), nullable=False, server_default="fernet"),  # fernet, aes-256-gcm
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),  # NULL = current version
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Index for current key version (revoked_at IS NULL)
    op.create_index(
        "idx_encryption_keys_current",
        "encryption_key_versions",
        ["tenant_id", "revoked_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),  # Partial: only current versions
        schema="triage",
    )

    # ========== RLS POLICIES ==========
    # (messages, conversations, outbox_events, pii_tokens are covered by the
    # rls_tenant_policy loop in 0001; only encryption_key_versions is new here)

    # RLS Policy for encryption_key_versions: tenant isolation
    op.execute(
        """
        CREATE POLICY encryption_key_versions_tenant_isolation ON triage.encryption_key_versions
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )

    op.execute("ALTER TABLE triage.encryption_key_versions ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Drop Sprint 1 additions (tables created in 0001 are dropped there)."""
    op.execute("DROP POLICY IF EXISTS encryption_key_versions_tenant_isolation ON triage.encryption_key_versions")

    op.drop_table("encryption_key_versions", schema="triage")
