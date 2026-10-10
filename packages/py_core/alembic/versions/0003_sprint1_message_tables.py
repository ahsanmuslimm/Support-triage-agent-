"""Sprint 1: Message ingestion tables with idempotency, encryption, PII handling.

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Sprint 1 message ingestion tables."""

    # Messages table (S1.1)
    # Composite PK: (tenant_id, id)
    # Idempotency unique index: (tenant_id, idempotency_key)
    op.create_table(
        "messages",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(50), nullable=False),  # email, chat, sms, api, zendesk
        sa.Column("source", sa.String(50), nullable=False),  # zendesk, widget, api
        sa.Column("body", sa.Text(), nullable=False),  # Plaintext for now (redacted)
        sa.Column("body_encrypted", postgresql.JSONB(), nullable=True),  # {"ciphertext": "...", "iv": "...", "dek_version": 1}
        sa.Column("language", sa.String(10), nullable=True),  # Detected language code
        sa.Column("provider_message_id", sa.String(255), nullable=True),  # External ID (e.g., Zendesk comment ID)
        sa.Column("sender_id", sa.String(255), nullable=True),  # Normalized sender identifier
        sa.Column("idempotency_key", sa.String(255), nullable=False),  # SHA256(tenant_id+provider_id or sender_id+body_hash)
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),  # Channel-specific metadata
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["triage.customers.tenant_id", "triage.customers.id"]),
        schema="triage",
    )

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

    # Conversations table (S1.9)
    # Composite PK: (tenant_id, id)
    op.create_table(
        "conversations",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=True),  # email, chat, sms, etc.
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),  # open, pending, resolved, escalated, closed
        sa.Column("priority", sa.String(50), nullable=True, server_default="normal"),  # low, normal, high, urgent
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),  # Denormalized count
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),  # Unread count
        sa.Column("intent_primary", sa.String(255), nullable=True),  # Primary classification intent
        sa.Column("intent_secondary", sa.String(255), nullable=True),  # Secondary intent
        sa.Column("confidence_score", sa.Float(), nullable=True),  # Classification confidence [0, 1]
        sa.Column("is_auto_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["triage.customers.tenant_id", "triage.customers.id"]),
        schema="triage",
    )

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

    # Outbox events table (S1.7)
    # Transactional write: every domain object change writes an event here
    # Outbox poller picks up unpublished events and delivers them
    op.create_table(
        "outbox_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("aggregate_type", sa.String(50), nullable=False),  # message, conversation, customer
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),  # ID of the object that changed
        sa.Column("event_type", sa.String(100), nullable=False),  # message.ingested, conversation.coalesced, customer.identified
        sa.Column("payload", postgresql.JSONB(), nullable=False),  # Full event data (for consumer)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),  # NULL = unpublished, not NULL = published
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Index for outbox polling (find unpublished events)
    op.create_index(
        "idx_outbox_events_unpublished",
        "outbox_events",
        ["tenant_id", "published_at"],
        sa.text("WHERE published_at IS NULL"),  # Partial index: only unpublished
        schema="triage",
    )

    # Index for outbox by aggregate (for ordering guarantees)
    op.create_index(
        "idx_outbox_events_aggregate",
        "outbox_events",
        ["tenant_id", "aggregate_type", "aggregate_id", "created_at"],
        schema="triage",
    )

    # PII tokens vault (S1.6)
    # Stores redacted PII: hash -> redacted token mapping
    # PII text never stored directly in messages or logs
    op.create_table(
        "pii_tokens",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("pii_type", sa.String(50), nullable=False),  # EMAIL, PHONE, CREDIT_CARD, SSN, etc.
        sa.Column("pii_hash", sa.String(64), nullable=False),  # SHA256(pii_value) - never store plaintext
        sa.Column("token", sa.String(64), nullable=False),  # [PII_EMAIL_xyz123...]
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),  # Link to originating message (optional)
        sa.Column("encrypted_value", sa.String(1024), nullable=True),  # Fernet-encrypted PII value (for recovery)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

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
        sa.text("WHERE revoked_at IS NULL"),  # Partial: only current versions
        schema="triage",
    )

    # ========== RLS POLICIES ==========

    # RLS Policy for messages: tenant isolation
    op.execute(
        """
        CREATE POLICY messages_tenant_isolation ON triage.messages
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )

    op.execute("ALTER TABLE triage.messages ENABLE ROW LEVEL SECURITY")

    # RLS Policy for conversations: tenant isolation
    op.execute(
        """
        CREATE POLICY conversations_tenant_isolation ON triage.conversations
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )

    op.execute("ALTER TABLE triage.conversations ENABLE ROW LEVEL SECURITY")

    # RLS Policy for outbox_events: tenant isolation
    op.execute(
        """
        CREATE POLICY outbox_events_tenant_isolation ON triage.outbox_events
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )

    op.execute("ALTER TABLE triage.outbox_events ENABLE ROW LEVEL SECURITY")

    # RLS Policy for pii_tokens: tenant isolation
    op.execute(
        """
        CREATE POLICY pii_tokens_tenant_isolation ON triage.pii_tokens
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )

    op.execute("ALTER TABLE triage.pii_tokens ENABLE ROW LEVEL SECURITY")

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
    """Drop Sprint 1 tables."""
    op.execute("DROP POLICY IF EXISTS messages_tenant_isolation ON triage.messages")
    op.execute("DROP POLICY IF EXISTS conversations_tenant_isolation ON triage.conversations")
    op.execute("DROP POLICY IF EXISTS outbox_events_tenant_isolation ON triage.outbox_events")
    op.execute("DROP POLICY IF EXISTS pii_tokens_tenant_isolation ON triage.pii_tokens")
    op.execute("DROP POLICY IF EXISTS encryption_key_versions_tenant_isolation ON triage.encryption_key_versions")

    op.drop_table("messages", schema="triage")
    op.drop_table("conversations", schema="triage")
    op.drop_table("outbox_events", schema="triage")
    op.drop_table("pii_tokens", schema="triage")
    op.drop_table("encryption_key_versions", schema="triage")
