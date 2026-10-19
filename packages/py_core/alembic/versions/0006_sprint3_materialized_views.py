"""Sprint 3: Materialized views for analytics dashboards and metrics.

Revision ID: 0006
Revises: 0005
Create Date: 2024-01-06 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create materialized views for Sprint 3 analytics dashboards."""

    # ========== S3.9: MATERIALIZED VIEWS FOR ANALYTICS ==========

    # Daily triage summary: count of triages, escalations, autonomy decisions
    # (decisions live on triage_runs.action: auto_resolve | escalate | tool_execute | human_review)
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_triage_daily_summary AS
        SELECT
            DATE(r.created_at) as triage_date,
            r.tenant_id,
            COUNT(*) as total_triages,
            SUM(CASE WHEN r.action = 'escalate' THEN 1 ELSE 0 END) as escalated_count,
            SUM(CASE WHEN r.action = 'auto_resolve' THEN 1 ELSE 0 END) as handled_count,
            SUM(CASE WHEN r.action = 'human_review' THEN 1 ELSE 0 END) as review_count,
            ROUND(100.0 * SUM(CASE WHEN r.action = 'escalate' THEN 1 ELSE 0 END) / COUNT(*), 2) as escalation_pct,
            ROUND(100.0 * SUM(CASE WHEN r.action = 'auto_resolve' THEN 1 ELSE 0 END) / COUNT(*), 2) as autonomy_pct
        FROM triage.triage_runs r
        WHERE r.created_at >= NOW() - INTERVAL '90 days'
        GROUP BY DATE(r.created_at), r.tenant_id
        WITH DATA;
    """)

    # Intent accuracy daily: intent classification confidence per intent per day
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_intent_accuracy_daily AS
        SELECT
            DATE(c.created_at) as analysis_date,
            c.tenant_id,
            c.intent_primary as intent,
            COUNT(*) as total_predictions,
            SUM(CASE WHEN c.confidence_score >= 0.8 THEN 1 ELSE 0 END) as high_confidence_count,
            ROUND(100.0 * SUM(CASE WHEN c.confidence_score >= 0.8 THEN 1 ELSE 0 END) / COUNT(*), 2) as accuracy_pct
        FROM triage.conversations c
        WHERE c.created_at >= NOW() - INTERVAL '30 days' AND c.intent_primary IS NOT NULL
        GROUP BY DATE(c.created_at), c.tenant_id, c.intent_primary
        WITH DATA;
    """)

    # Agent/autonomy performance: decision rate, resolution metrics per action
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_agent_performance_daily AS
        SELECT
            DATE(r.created_at) as performance_date,
            r.tenant_id,
            r.action,
            COUNT(*) as decision_count,
            ROUND((AVG(r.latency_ms) / 1000.0)::NUMERIC, 2) as avg_latency_sec,
            ROUND(AVG(r.intent_confidence), 3) as avg_confidence,
            SUM(CASE WHEN r.status = 'failed' THEN 1 ELSE 0 END) as failure_count
        FROM triage.triage_runs r
        WHERE r.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(r.created_at), r.tenant_id, r.action
        WITH DATA;
    """)

    # Customer outcomes: resolution success by customer segment
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_customer_outcomes_daily AS
        SELECT
            DATE(c.created_at) as outcome_date,
            c.tenant_id,
            CASE
                WHEN hsa.health_label = 'at_risk' THEN 'at_risk'
                WHEN cu.ltv_cents > 500000 THEN 'high_value'
                WHEN cu.tier = 'premium' OR cu.tier = 'enterprise' THEN 'loyal'
                ELSE 'standard'
            END as customer_segment,
            COUNT(DISTINCT c.id) as conversation_count,
            COUNT(DISTINCT c.customer_id) as unique_customers,
            ROUND(AVG(EXTRACT(EPOCH FROM (c.updated_at - c.created_at))), 2) as avg_resolution_time_sec,
            ROUND(100.0 * SUM(CASE WHEN c.status = 'resolved' THEN 1 ELSE 0 END) / COUNT(*), 2) as resolved_pct,
            ROUND(100.0 * SUM(CASE WHEN c.is_auto_resolved THEN 1 ELSE 0 END) / COUNT(*), 2) as auto_resolved_pct
        FROM triage.conversations c
        LEFT JOIN triage.health_score_audits hsa
            ON c.tenant_id = hsa.tenant_id AND c.customer_id::TEXT = hsa.customer_id
        LEFT JOIN triage.customers cu
            ON c.tenant_id = cu.tenant_id AND c.customer_id = cu.id
        WHERE c.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY
            DATE(c.created_at),
            c.tenant_id,
            CASE
                WHEN hsa.health_label = 'at_risk' THEN 'at_risk'
                WHEN cu.ltv_cents > 500000 THEN 'high_value'
                WHEN cu.tier = 'premium' OR cu.tier = 'enterprise' THEN 'loyal'
                ELSE 'standard'
            END
        WITH DATA;
    """)

    # Anomaly summary: recent anomalies and drift alerts
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_anomalies_recent AS
        SELECT
            a.tenant_id,
            a.metric_name,
            a.current_value,
            a.expected_value,
            a.deviation_sigma,
            a.severity,
            a.created_at,
            m.recorded_at as metric_recorded_at,
            ROW_NUMBER() OVER (PARTITION BY a.tenant_id, a.metric_name ORDER BY a.created_at DESC) as recency_rank
        FROM triage.anomaly_events a
        LEFT JOIN triage.metric_history m ON a.tenant_id = m.tenant_id AND a.metric_name = m.metric_name
        WHERE a.created_at >= NOW() - INTERVAL '7 days'
        WITH DATA;
    """)

    # Model performance tracking
    op.execute("""
        CREATE MATERIALIZED VIEW triage.v_model_performance_history AS
        SELECT
            m.tenant_id,
            m.metric_name,
            DATE(m.recorded_at) as metric_date,
            ROUND(AVG(m.metric_value)::NUMERIC, 4) as avg_metric_value,
            ROUND(MIN(m.metric_value)::NUMERIC, 4) as min_metric_value,
            ROUND(MAX(m.metric_value)::NUMERIC, 4) as max_metric_value,
            COUNT(*) as measurement_count
        FROM triage.metric_history m
        WHERE m.recorded_at >= NOW() - INTERVAL '90 days'
        GROUP BY m.tenant_id, m.metric_name, DATE(m.recorded_at)
        WITH DATA;
    """)

    # Create indices on materialized views for faster queries
    op.execute("""
        CREATE INDEX idx_v_triage_daily_summary_tenant_date
        ON triage.v_triage_daily_summary (tenant_id, triage_date DESC);
    """)

    op.execute("""
        CREATE INDEX idx_v_agent_performance_daily_tenant_date
        ON triage.v_agent_performance_daily (tenant_id, performance_date DESC);
    """)

    op.execute("""
        CREATE INDEX idx_v_customer_outcomes_daily_tenant_segment
        ON triage.v_customer_outcomes_daily (tenant_id, customer_segment);
    """)

    op.execute("""
        CREATE INDEX idx_v_anomalies_recent_tenant_severity
        ON triage.v_anomalies_recent (tenant_id, severity DESC);
    """)

    # Note: pg_cron refresh scheduling would be done via a separate Celery task or direct DB job.
    # For now, include a comment showing the intended refresh schedule:
    op.execute("""
        -- Intended refresh schedules (to be configured via pg_cron or application scheduler):
        -- SELECT cron.schedule('refresh-triage-daily-summary', '*/15 * * * *',
        --     'REFRESH MATERIALIZED VIEW CONCURRENTLY triage.v_triage_daily_summary');
        -- SELECT cron.schedule('refresh-agent-performance-daily', '*/15 * * * *',
        --     'REFRESH MATERIALIZED VIEW CONCURRENTLY triage.v_agent_performance_daily');
        -- SELECT cron.schedule('refresh-customer-outcomes-daily', '*/15 * * * *',
        --     'REFRESH MATERIALIZED VIEW CONCURRENTLY triage.v_customer_outcomes_daily');
        -- SELECT cron.schedule('refresh-anomalies-recent', '*/5 * * * *',
        --     'REFRESH MATERIALIZED VIEW CONCURRENTLY triage.v_anomalies_recent');
        -- SELECT cron.schedule('refresh-model-performance-history', '*/30 * * * *',
        --     'REFRESH MATERIALIZED VIEW CONCURRENTLY triage.v_model_performance_history');
    """)


def downgrade() -> None:
    """Drop materialized views."""

    views_to_drop = [
        "v_model_performance_history",
        "v_anomalies_recent",
        "v_customer_outcomes_daily",
        "v_agent_performance_daily",
        "v_intent_accuracy_daily",
        "v_triage_daily_summary",
    ]

    for view in views_to_drop:
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS triage.{view} CASCADE;")
