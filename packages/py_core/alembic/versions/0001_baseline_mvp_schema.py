"""Baseline MVP schema with all tables, RLS policies, and indexes.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create baseline MVP schema."""
    # Create pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create triage schema
    op.execute("CREATE SCHEMA IF NOT EXISTS triage")

    # Create ENUM types
    op.execute(
        """
        CREATE TYPE triage.channel_type AS ENUM (
            'email',
            'chat',
            'sms',
            'voice',
            'social',
            'api'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.conversation_status AS ENUM (
            'open',
            'resolved',
            'escalated',
            'pending_customer_response',
            'reopened'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.resolution_type AS ENUM (
            'autonomous',
            'human_draft',
            'escalated',
            'clarification'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.autonomy_level AS ENUM (
            'full_auto',
            'draft_review',
            'human_required',
            'blocked'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.customer_tier AS ENUM (
            'free',
            'standard',
            'premium',
            'enterprise'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.audit_action AS ENUM (
            'create',
            'read',
            'update',
            'delete',
            'execute'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.kb_audience AS ENUM (
            'public',
            'internal',
            'premium'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE triage.feedback_type AS ENUM (
            'helpful',
            'incorrect',
            'incomplete',
            'too_slow',
            'escalated_unnecessarily'
        )
        """
    )

    # Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="triage",
    )

    # Customers table (multi-tenant)
    op.create_table(
        "customers",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("email_hash", sa.String(255), nullable=False),
        sa.Column("phone_hash", sa.String(255), nullable=True),
        sa.Column("name_pseudonym", sa.String(255), nullable=True),
        sa.Column("ltv_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tier", sa.Enum("free", "standard", "premium", "enterprise", name="customer_tier", schema="triage"), nullable=False, server_default="standard"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Channels table (multi-tenant)
    op.create_table(
        "channels",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("type", sa.Enum("email", "chat", "sms", "voice", "social", "api", name="channel_type", schema="triage"), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Intents table (multi-tenant)
    op.create_table(
        "intents",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("autonomy_default", sa.String(50), nullable=False, server_default="draft_review"),
        sa.Column("human_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.UniqueConstraint("tenant_id", "key", name="uq_intents_tenant_key"),
        schema="triage",
    )

    # Intent examples table (multi-tenant)
    op.create_table(
        "intent_examples",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.text(), nullable=True),  # pgvector halfvec type
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "intent_id"], ["triage.intents.tenant_id", "triage.intents.id"]),
        schema="triage",
    )

    # Autonomy settings table (multi-tenant)
    op.create_table(
        "autonomy_settings",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(50), nullable=True),
        sa.Column("segment", sa.String(100), nullable=True),
        sa.Column("level", sa.String(50), nullable=False),
        sa.Column("threshold_auto", sa.Numeric(5, 3), nullable=False, server_default="0.95"),
        sa.Column("threshold_draft", sa.Numeric(5, 3), nullable=False, server_default="0.80"),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "intent_id"], ["triage.intents.tenant_id", "triage.intents.id"]),
        schema="triage",
    )

    # Conversations table (multi-tenant)
    op.create_table(
        "conversations",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Enum("open", "resolved", "escalated", "pending_customer_response", "reopened", name="conversation_status", schema="triage"), nullable=False, server_default="open"),
        sa.Column("resolution_type", sa.String(50), nullable=True),
        sa.Column("reopened_72h", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("csat_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["triage.customers.tenant_id", "triage.customers.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "channel_id"], ["triage.channels.tenant_id", "triage.channels.id"]),
        schema="triage",
    )

    # Messages table (multi-tenant)
    op.create_table(
        "messages",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(50), nullable=False),  # inbound, outbound
        sa.Column("role", sa.String(50), nullable=False),  # customer, agent, system
        sa.Column("body_ciphertext", sa.Text(), nullable=False),
        sa.Column("body_iv", sa.String(255), nullable=False),
        sa.Column("dek_version", sa.Integer(), nullable=False),
        sa.Column("pseudonymized_body", sa.Text(), nullable=True),
        sa.Column("provider_msg_id", sa.String(255), nullable=True, unique=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("coalesced_into", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        schema="triage",
    )

    # Triage runs table (multi-tenant)
    op.create_table(
        "triage_runs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("decision", sa.String(50), nullable=True),
        sa.Column("autonomy_level", sa.String(50), nullable=False),
        sa.Column("guard_scores", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("llm_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["triage.messages.tenant_id", "triage.messages.id"]),
        schema="triage",
    )

    # Predictions table (multi-tenant)
    op.create_table(
        "predictions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"], ["triage.triage_runs.tenant_id", "triage.triage_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "intent_id"], ["triage.intents.tenant_id", "triage.intents.id"]),
        schema="triage",
    )

    # Entities table (multi-tenant)
    op.create_table(
        "entities",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("raw_value_hash", sa.String(255), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("owner_match", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"], ["triage.triage_runs.tenant_id", "triage.triage_runs.id"]),
        schema="triage",
    )

    # Response drafts table (multi-tenant)
    op.create_table(
        "response_drafts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body_ciphertext", sa.Text(), nullable=False),
        sa.Column("body_iv", sa.String(255), nullable=False),
        sa.Column("dek_version", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=True),
        sa.Column("edit_ratio", sa.Numeric(5, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"], ["triage.triage_runs.tenant_id", "triage.triage_runs.id"]),
        schema="triage",
    )

    # Handoff packets table (multi-tenant)
    op.create_table(
        "handoff_packets",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"], ["triage.triage_runs.tenant_id", "triage.triage_runs.id"]),
        schema="triage",
    )

    # Knowledge Base sources (multi-tenant)
    op.create_table(
        "kb_sources",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # KB documents (multi-tenant)
    op.create_table(
        "kb_documents",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "source_id"], ["triage.kb_sources.tenant_id", "triage.kb_sources.id"]),
        schema="triage",
    )

    # KB chunks (multi-tenant)
    op.create_table(
        "kb_chunks",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.text(), nullable=True),  # pgvector halfvec type
        sa.Column("audience", sa.String(50), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "document_id"], ["triage.kb_documents.tenant_id", "triage.kb_documents.id"]),
        schema="triage",
    )

    # Action definitions (multi-tenant)
    op.create_table(
        "action_definitions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.UniqueConstraint("tenant_id", "key", name="uq_action_defs_tenant_key"),
        schema="triage",
    )

    # Action executions (multi-tenant)
    op.create_table(
        "action_executions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("action_def_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "action_def_id"], ["triage.action_definitions.tenant_id", "triage.action_definitions.id"]),
        schema="triage",
    )

    # Assignments (multi-tenant)
    op.create_table(
        "assignments",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        schema="triage",
    )

    # Feedback (multi-tenant)
    op.create_table(
        "feedback",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        schema="triage",
    )

    # Outbox events (for event sourcing)
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Audit log (append-only)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # PII tokens vault
    op.create_table(
        "pii_tokens",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("iv", sa.String(255), nullable=False),
        sa.Column("dek_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Create indexes
    op.create_index("idx_customers_tenant_email", "customers", ["tenant_id", "email_hash"], schema="triage")
    op.create_index("idx_conversations_tenant_customer", "conversations", ["tenant_id", "customer_id"], schema="triage")
    op.create_index("idx_messages_conversation", "messages", ["tenant_id", "conversation_id"], schema="triage")
    op.create_index("idx_triage_runs_conversation", "triage_runs", ["tenant_id", "conversation_id"], schema="triage")
    op.create_index("idx_predictions_run", "predictions", ["tenant_id", "run_id"], schema="triage")
    op.create_index("idx_kb_chunks_document", "kb_chunks", ["tenant_id", "document_id"], schema="triage")
    op.create_index("idx_audit_log_tenant_created", "audit_log", ["tenant_id", "created_at"], schema="triage")

    # HNSW indexes for vector similarity search
    op.execute(
        """
        CREATE INDEX idx_intent_examples_embedding 
        ON triage.intent_examples 
        USING hnsw (embedding vector_ip_ops)
        WHERE embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_kb_chunks_embedding 
        ON triage.kb_chunks 
        USING hnsw (embedding vector_ip_ops)
        WHERE embedding IS NOT NULL
        """
    )

    # Enable RLS on multi-tenant tables
    multi_tenant_tables = [
        "customers",
        "channels",
        "intents",
        "intent_examples",
        "autonomy_settings",
        "conversations",
        "messages",
        "triage_runs",
        "predictions",
        "entities",
        "response_drafts",
        "handoff_packets",
        "kb_sources",
        "kb_documents",
        "kb_chunks",
        "action_definitions",
        "action_executions",
        "assignments",
        "feedback",
        "outbox_events",
        "audit_log",
        "pii_tokens",
    ]

    for table_name in multi_tenant_tables:
        op.execute(f"ALTER TABLE triage.{table_name} ENABLE ROW LEVEL SECURITY")

        # Create RLS policy
        op.execute(
            f"""
            CREATE POLICY rls_tenant_policy ON triage.{table_name}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """
        )


def downgrade() -> None:
    """Drop all tables and types."""
    # Drop policies first
    multi_tenant_tables = [
        "customers",
        "channels",
        "intents",
        "intent_examples",
        "autonomy_settings",
        "conversations",
        "messages",
        "triage_runs",
        "predictions",
        "entities",
        "response_drafts",
        "handoff_packets",
        "kb_sources",
        "kb_documents",
        "kb_chunks",
        "action_definitions",
        "action_executions",
        "assignments",
        "feedback",
        "outbox_events",
        "audit_log",
        "pii_tokens",
    ]

    for table_name in multi_tenant_tables:
        op.execute(f"DROP POLICY rls_tenant_policy ON triage.{table_name}")

    # Drop tables
    op.execute("DROP SCHEMA triage CASCADE")
