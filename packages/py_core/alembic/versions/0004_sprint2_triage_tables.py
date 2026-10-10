"""Sprint 2: Triage graph, classification, autonomy, and entity extraction tables.

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-04 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Sprint 2 triage, classification, autonomy, and entity tables."""

    # ========== INTENT CLASSIFICATION TABLES ==========

    # Intent embeddings (avg of training examples per intent)
    op.create_table(
        "intent_embeddings",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("intent_name", sa.String(100), primary_key=True),
        sa.Column("embedding", postgresql.JSON(), nullable=False),  # vector(384) represented as JSON array
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Intent training examples (golden set for k-NN classifier)
    op.create_table(
        "intent_examples",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("intent_name", sa.String(100), nullable=False),
        sa.Column("example_text", sa.Text(), nullable=False),
        sa.Column("is_golden", sa.Boolean(), nullable=False, server_default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    op.create_index(
        "idx_intent_examples_tenant_intent",
        "intent_examples",
        ["tenant_id", "intent_name"],
        schema="triage",
    )

    # ========== TRIAGE RUN RESULTS ==========

    # Triage runs (output of agent graph execution)
    op.create_table(
        "triage_runs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("top_intent", sa.String(100), nullable=True),
        sa.Column("intent_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("autonomy_level", sa.Integer(), nullable=True),  # 0-3
        sa.Column("action", sa.String(50), nullable=True),  # auto_resolve, escalate, tool_execute, human_review
        sa.Column("tool_executed", sa.String(100), nullable=True),
        sa.Column("tool_result", postgresql.JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("reasoning", postgresql.JSONB(), nullable=False, server_default="[]"),  # Array of reasoning steps
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),  # pending, completed, failed
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["triage.messages.tenant_id", "triage.messages.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["triage.conversations.tenant_id", "triage.conversations.id"]),
        schema="triage",
    )

    op.create_index(
        "idx_triage_runs_tenant_message",
        "triage_runs",
        ["tenant_id", "message_id"],
        schema="triage",
    )

    op.create_index(
        "idx_triage_runs_tenant_conversation",
        "triage_runs",
        ["tenant_id", "conversation_id"],
        schema="triage",
    )

    # ========== ENTITY EXTRACTION ==========

    # Extracted entities (from message processing)
    op.create_table(
        "extracted_entities",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),  # ORDER_ID, AMOUNT, EMAIL, PHONE, ACCOUNT_ID, etc.
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False),  # 0-1
        sa.Column("linked_id", sa.BigInteger(), nullable=True),  # Foreign key to customer/order record
        sa.Column("is_pii", sa.Boolean(), nullable=False, server_default=False),
        sa.Column("pseudonym", sa.String(255), nullable=True),  # VAULT_xyz... for PII
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["triage.messages.tenant_id", "triage.messages.id"]),
        schema="triage",
    )

    op.create_index(
        "idx_extracted_entities_tenant_message",
        "extracted_entities",
        ["tenant_id", "message_id"],
        schema="triage",
    )

    op.create_index(
        "idx_extracted_entities_tenant_type",
        "extracted_entities",
        ["tenant_id", "entity_type"],
        schema="triage",
    )

    # ========== AUTONOMY & POLICY ==========

    # Autonomy policies (per-tenant, per-intent)
    op.create_table(
        "autonomy_policies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("intent", sa.String(100), nullable=False),
        sa.Column("autonomy_level", sa.Integer(), nullable=False),  # 0=read_only, 1=suggest, 2=confirm, 3=auto
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "intent", name="uq_autonomy_policies_tenant_intent"),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Autonomy promotions (audit trail)
    op.create_table(
        "autonomy_promotions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("intent", sa.String(100), nullable=False),
        sa.Column("from_level", sa.Integer(), nullable=False),
        sa.Column("to_level", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("groundedness", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("admin_approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # ========== RLS POLICIES ==========

    # RLS for intent_embeddings
    op.execute(
        """
        CREATE POLICY intent_embeddings_tenant_isolation ON triage.intent_embeddings
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.intent_embeddings ENABLE ROW LEVEL SECURITY")

    # RLS for intent_examples
    op.execute(
        """
        CREATE POLICY intent_examples_tenant_isolation ON triage.intent_examples
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.intent_examples ENABLE ROW LEVEL SECURITY")

    # RLS for triage_runs
    op.execute(
        """
        CREATE POLICY triage_runs_tenant_isolation ON triage.triage_runs
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.triage_runs ENABLE ROW LEVEL SECURITY")

    # RLS for extracted_entities
    op.execute(
        """
        CREATE POLICY extracted_entities_tenant_isolation ON triage.extracted_entities
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.extracted_entities ENABLE ROW LEVEL SECURITY")

    # RLS for autonomy_policies
    op.execute(
        """
        CREATE POLICY autonomy_policies_tenant_isolation ON triage.autonomy_policies
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.autonomy_policies ENABLE ROW LEVEL SECURITY")

    # RLS for autonomy_promotions
    op.execute(
        """
        CREATE POLICY autonomy_promotions_tenant_isolation ON triage.autonomy_promotions
        FOR ALL
        USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        WITH CHECK (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)
        """
    )
    op.execute("ALTER TABLE triage.autonomy_promotions ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Drop Sprint 2 tables."""
    op.execute("DROP POLICY IF EXISTS intent_embeddings_tenant_isolation ON triage.intent_embeddings")
    op.execute("DROP POLICY IF EXISTS intent_examples_tenant_isolation ON triage.intent_examples")
    op.execute("DROP POLICY IF EXISTS triage_runs_tenant_isolation ON triage.triage_runs")
    op.execute("DROP POLICY IF EXISTS extracted_entities_tenant_isolation ON triage.extracted_entities")
    op.execute("DROP POLICY IF EXISTS autonomy_policies_tenant_isolation ON triage.autonomy_policies")
    op.execute("DROP POLICY IF EXISTS autonomy_promotions_tenant_isolation ON triage.autonomy_promotions")

    op.drop_table("autonomy_promotions", schema="triage")
    op.drop_table("autonomy_policies", schema="triage")
    op.drop_table("extracted_entities", schema="triage")
    op.drop_table("triage_runs", schema="triage")
    op.drop_table("intent_examples", schema="triage")
    op.drop_table("intent_embeddings", schema="triage")
