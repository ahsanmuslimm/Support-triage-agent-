"""Sprint 3: Enrichment layer tables (customer, order, billing, sentiment, knowledge gap, feedback, learning).

Revision ID: 0005
Revises: 0004
Create Date: 2024-01-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Sprint 3 enrichment tables."""

    # ========== S3.1-S3.3: ENRICHMENT CACHE TABLES ==========

    # Customer enrichment cache (S3.1)
    op.create_table(
        "customer_enrichment_cache",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("context_data", postgresql.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "customer_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_customer_enrichment_expires",
        "customer_enrichment_cache",
        ["expires_at"],
        schema="triage",
    )

    # Order enrichment cache (S3.2)
    op.create_table(
        "order_enrichment_cache",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("context_data", postgresql.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "customer_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Billing enrichment cache (S3.3)
    op.create_table(
        "billing_enrichment_cache",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("context_data", postgresql.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "customer_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # ========== S3.6: SENTIMENT & NPS TABLES ==========

    # NPS surveys and sentiment history
    op.create_table(
        "nps_surveys",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),  # 0-10
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_nps_surveys_tenant_customer",
        "nps_surveys",
        ["tenant_id", "customer_id"],
        schema="triage",
    )
    op.create_index(
        "idx_nps_surveys_sent_at",
        "nps_surveys",
        ["sent_at"],
        schema="triage",
    )

    # Sentiment analysis results (cached)
    op.create_table(
        "sentiment_analysis_cache",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column("sentiment", sa.String(20), nullable=False),  # positive, neutral, negative
        sa.Column("polarity_score", sa.Float(), nullable=False),  # -1.0 to 1.0
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "conversation_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # ========== S3.4: HEALTH SCORING & MODEL TABLES ==========

    # Model versions and metadata (S3.4)
    op.create_table(
        "model_versions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("model_name", sa.String(100), nullable=False),  # e.g., 'health_scorer', 'intent_classifier'
        sa.Column("version", sa.String(50), nullable=False),  # semver: v1.2.3
        sa.Column("model_path", sa.String(500), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("auc", sa.Float(), nullable=True),
        sa.Column("training_samples", sa.Integer(), nullable=True),
        sa.Column("training_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=False),
        sa.Column("is_candidate", sa.Boolean(), nullable=False, server_default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_model_versions_tenant_name_active",
        "model_versions",
        ["tenant_id", "model_name", "is_active"],
        schema="triage",
    )

    # Health score audit log (for explainability tracking)
    op.create_table(
        "health_score_audits",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=False),  # 0.0 - 1.0
        sa.Column("health_label", sa.String(20), nullable=False),  # 'healthy', 'at_risk'
        sa.Column("shap_drivers", postgresql.JSON(), nullable=True),  # Top 3 feature drivers
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_health_score_audits_tenant_created",
        "health_score_audits",
        ["tenant_id", "created_at"],
        schema="triage",
    )

    # ========== S3.5: KNOWLEDGE GAP TABLES ==========

    op.create_table(
        "knowledge_gap_analysis",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),  # 0.0 - 1.0
        sa.Column("query_count_7d", sa.Integer(), nullable=False),
        sa.Column("resolved_count_7d", sa.Integer(), nullable=False),
        sa.Column("gap_rank", sa.Integer(), nullable=False),  # 1-10
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_knowledge_gap_tenant_analyzed",
        "knowledge_gap_analysis",
        ["tenant_id", "analyzed_at"],
        schema="triage",
    )

    # ========== S3.8: FEEDBACK & LEARNING TABLES ==========

    # Feedback events (thumbs up/down, tags, escalation resolved)
    op.create_table(
        "feedback_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column("feedback_type", sa.String(50), nullable=False),  # thumbs_up, thumbs_down, tag, escalation_resolved
        sa.Column("value", sa.Integer(), nullable=True),  # Rating 1-5
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_feedback_events_tenant_created",
        "feedback_events",
        ["tenant_id", "created_at"],
        schema="triage",
    )

    # A/B test assignments
    op.create_table(
        "ab_test_assignments",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("experiment_id", sa.String(100), nullable=False),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column("variant", sa.String(50), nullable=False),  # control, treatment
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_ab_test_assignments_experiment",
        "ab_test_assignments",
        ["tenant_id", "experiment_id"],
        schema="triage",
    )

    # A/B test outcomes
    op.create_table(
        "ab_test_outcomes",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("experiment_id", sa.String(100), nullable=False),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column("outcome_metric", sa.String(100), nullable=False),  # autonomy_decision, resolution_time_sec
        sa.Column("outcome_value", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )

    # Model metric history for drift detection
    op.create_table(
        "metric_history",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("metric_name", sa.String(100), nullable=False),  # accuracy, auc, precision, recall
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_metric_history_tenant_metric_date",
        "metric_history",
        ["tenant_id", "metric_name", "recorded_at"],
        schema="triage",
    )

    # Anomaly events (drift detection alerts)
    op.create_table(
        "anomaly_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=False),
        sa.Column("deviation_sigma", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),  # low, high, critical
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index(
        "idx_anomaly_events_tenant_severity",
        "anomaly_events",
        ["tenant_id", "severity"],
        schema="triage",
    )


def downgrade() -> None:
    """Drop Sprint 3 enrichment tables."""

    tables_to_drop = [
        "anomaly_events",
        "metric_history",
        "ab_test_outcomes",
        "ab_test_assignments",
        "feedback_events",
        "knowledge_gap_analysis",
        "health_score_audits",
        "model_versions",
        "sentiment_analysis_cache",
        "nps_surveys",
        "billing_enrichment_cache",
        "order_enrichment_cache",
        "customer_enrichment_cache",
    ]

    for table in tables_to_drop:
        op.drop_table(table, schema="triage")
