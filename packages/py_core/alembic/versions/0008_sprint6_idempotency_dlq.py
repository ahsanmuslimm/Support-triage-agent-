"""Sprint 6: Idempotency & DLQ tables (S6.3)."""
import sqlalchemy as sa
from alembic import op


def upgrade():
    """Create idempotency_records and dlq_events tables."""

    # Idempotency records (insert-first strategy, fast path + slow path)
    op.create_table(
        "idempotency_records",
        sa.Column("tenant_id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("result_json", sa.Text, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_first_attempt", sa.Boolean, default=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"], ondelete="CASCADE"),
        schema="triage",
    )

    op.create_index(
        "idx_idempotency_processed_at",
        "idempotency_records",
        ["processed_at"],
        schema="triage",
    )
    op.create_index(
        "idx_idempotency_event_type",
        "idempotency_records",
        ["event_type"],
        schema="triage",
    )

    # DLQ (persistent storage for failed events with replay capability)
    op.create_table(
        "dlq_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("original_event_id", sa.String(255), nullable=False),
        sa.Column("original_event", sa.Text, nullable=False),  # JSON
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("error_type", sa.String(100)),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"], ondelete="CASCADE"),
        schema="triage",
    )

    op.create_index(
        "idx_dlq_created_at",
        "dlq_events",
        ["created_at"],
        schema="triage",
    )
    op.create_index(
        "idx_dlq_replayed",
        "dlq_events",
        ["replayed_at"],
        postgresql_where=sa.text("replayed_at IS NULL"),
        schema="triage",
    )


def downgrade():
    """Drop idempotency_records and dlq_events tables."""
    op.drop_table("dlq_events", schema="triage")
    op.drop_table("idempotency_records", schema="triage")
