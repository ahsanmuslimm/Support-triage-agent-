# Sprint 4 Implementation Plan: Proactive Triggers & Escalation

**Date:** January 2026  
**Status:** PENDING  
**Goal:** Transform platform from reactive (respond) to proactive (detect, escalate, improve). Implement 10 deliverables (S4.1–S4.10).

---

## Executive Summary

Sprint 4 implements 6 batches of features across 5 new modules + 1 extension:

| Batch | Deliverables | Purpose | Files |
|-------|--------------|---------|-------|
| **B1: Anomaly Detection** | S4.1 | Real-time risk signal detection (EWMA + Isolation Forest) | `anomaly/` (2 files) |
| **B2: Proactive Outreach** | S4.2 | Campaign triggers + A/B testing framework | `outreach/` (3 files) |
| **B3: Escalation Rules & Override** | S4.3, S4.5, S4.8 | Confidence-based escalation, SLA management, handoff | `escalation/` (5 files) |
| **B4: Multi-Channel Routing** | S4.6 | Slack/email/PagerDuty dispatcher, on-call sync | `escalation/router.py` (1 file) |
| **B5: Monitoring & Alerting** | S4.4, S4.9 | Prometheus metrics, Grafana dashboards, AlertManager | `monitoring/` (3 files) |
| **B6: Feedback Loop & Acceptance** | S4.7, S4.10 | Extend feedback module, E2E scenarios, golden set | Extend `feedback/`, `tests/` (2 files) |

**Total Files:** 19 Python files + 3 config files + 2 test files = 24  
**Migrations:** 1 (0007_sprint4_escalation_tables.py)  
**New Tables:** 5 (escalation_queue, escalation_audit, override_reason, feedback_signals, context_handoff)  
**Tests:** 40+ unit tests + 6 E2E scenarios + golden set

---

## Batch 1: Anomaly Detection & Risk Signals (S4.1)

**Deliverable:** Real-time EWMA + Isolation Forest ensemble detecting 6 anomaly types.

### Dependencies
- Sprint 3 enrichment context (S3.1–S3.3)
- Sprint 3 health scoring (S3.4)
- Sprint 3 analytics dashboards (S3.9) — uses v_triage_daily_summary

### Files to Create

#### 1.1 `services/api/src/triage/anomaly/__init__.py`
```python
from .detector import AnomalyDetector
from .models import AnomalySignal, SignalType

__all__ = ["AnomalyDetector", "AnomalySignal", "SignalType"]
```

#### 1.2 `services/api/src/triage/anomaly/models.py`
**Classes:**
- `SignalType(str, Enum)` — 6 types: `CHURN_SPIKE`, `FRAUD_PATTERN`, `COMPLAINT_SURGE`, `RESPONSE_DELAY`, `VOLUME_SPIKE`, `API_ERROR_RATE`
- `AnomalySignal(BaseModel)` — fields: signal_type, tenant_id, timestamp, value, threshold, deviation_sigma, confidence, metadata

**Tests:** Unit test for dataclass serialization, deserialization

#### 1.3 `services/api/src/triage/anomaly/detector.py`
**Class:** `AnomalyDetector`

**Key Methods:**
```python
class AnomalyDetector:
    def __init__(self, ewma_alpha: float = 0.1, isolation_forest_contamination: float = 0.05):
        # Load v_triage_daily_summary materialized view
        # Initialize EWMA smoother per signal type per tenant
        # Initialize Isolation Forest (sklearn)
        # Load baseline metrics from v_agent_performance_daily
        pass
    
    async def detect_signals(self, tenant_id: int) -> List[AnomalySignal]:
        """
        Detect anomalies in 6 dimensions:
        1. CHURN_SPIKE: health_score trend down + sentiment_negative_ratio up
        2. FRAUD_PATTERN: multiple chargeback flags + high_value_order_count spike
        3. COMPLAINT_SURGE: escalation_pct > 3σ above baseline
        4. RESPONSE_DELAY: avg_resolution_time_sec spike (>2σ)
        5. VOLUME_SPIKE: total_triages > 2σ above baseline
        6. API_ERROR_RATE: (error_count / total_requests) > 0.05
        
        Returns: List of AnomalySignal with confidence and metadata
        """
        pass
    
    async def _compute_ewma(self, tenant_id: int, signal_type: str) -> Tuple[float, float]:
        """
        EWMA smoothing: new_value = alpha * current + (1 - alpha) * previous
        Returns: (smoothed_value, deviation_sigma)
        """
        pass
    
    async def _score_isolation_forest(self, features: np.ndarray) -> np.ndarray:
        """
        Isolation Forest anomaly scores (-1.0 to 1.0, >0.5 = anomaly)
        """
        pass
    
    async def publish_webhook(self, signal: AnomalySignal) -> bool:
        """
        POST signal to escalation_queue webhook.
        Returns: success flag
        """
        pass
```

**Key Features:**
- Queries materialized views (v_triage_daily_summary, v_agent_performance_daily)
- Tracks EWMA baseline per signal per tenant
- Isolation Forest for multivariate anomaly scoring
- Webhook POST to escalation_queue
- Metrics logging (Prometheus counters)

**Tests:** 
- Unit: test_ewma_computation (verify alpha=0.1 math)
- Unit: test_isolation_forest_scoring (verify sklearn integration)
- Unit: test_signal_detection_all_6_types (mock data, check signal emission)
- Integration: test_detector_webhook_publish (mock HTTP)
- Performance: test_detector_latency_<2s (benchmark)

**Verify:** `pytest tests/unit/anomaly/ -v --tb=short`

---

## Batch 2: Proactive Outreach Triggers (S4.2)

**Deliverable:** Health/engagement/billing/loyalty campaigns triggered by enrichment context + A/B testing.

### Dependencies
- Sprint 3 enrichment (S3.1–S3.3)
- Sprint 3 health scoring (S3.4)

### Files to Create

#### 2.1 `services/api/src/triage/outreach/__init__.py`
```python
from .campaign_engine import CampaignEngine
from .ab_test_framework import ABTestFramework
from .models import Campaign, CampaignTemplate

__all__ = ["CampaignEngine", "ABTestFramework", "Campaign", "CampaignTemplate"]
```

#### 2.2 `services/api/src/triage/outreach/models.py`
**Classes:**
- `CampaignType(str, Enum)` — `HEALTH_CHECK`, `ENGAGEMENT`, `BILLING_WINBACK`, `LOYALTY_REWARD`
- `CampaignTemplate(BaseModel)` — fields: template_id, campaign_type, channels (list: email, in_app), subject_line, body_template (Jinja2), cta_text
- `Campaign(BaseModel)` — fields: id, tenant_id, customer_id, template_id, variant (A/B), created_at, sent_at, opened_at, clicked_at, converted_at
- `ABTestResult(BaseModel)` — fields: variant, open_rate, click_rate, conversion_rate, sample_size

**Tests:** Dataclass serialization, template rendering

#### 2.3 `services/api/src/triage/outreach/campaign_engine.py`
**Class:** `CampaignEngine`

**Key Methods:**
```python
class CampaignEngine:
    def __init__(self, template_store, messaging_service):
        # Load 4 campaign templates per type (e.g., 4x health_check variants)
        pass
    
    async def trigger_campaigns(self, tenant_id: int, customer_id: int, enrichment_context: dict) -> List[Campaign]:
        """
        Based on enrichment context, emit 0-N campaigns:
        1. HEALTH_CHECK: if health_score in (0.35, 0.65) → "We noticed changes in your account"
        2. ENGAGEMENT: if last_support_contact > 60 days AND is_active → "We miss you"
        3. BILLING_WINBACK: if payment_failed_count >= 1 AND churn_risk > 0.7 → "Update payment method"
        4. LOYALTY_REWARD: if order_count > 10 AND health_score > 0.8 AND not_vip → "Exclusive offer"
        
        For each triggered campaign, A/B randomize (variant A or B).
        Returns: List of Campaign records (database-inserted)
        """
        pass
    
    async def _should_trigger_health_check(self, context: dict) -> bool:
        """health_score in (0.35, 0.65)"""
        pass
    
    async def _should_trigger_engagement(self, context: dict) -> bool:
        """last_support_contact > 60 days AND is_active"""
        pass
    
    async def _should_trigger_billing_winback(self, context: dict) -> bool:
        """payment_failed_count >= 1 AND churn_risk > 0.7"""
        pass
    
    async def _should_trigger_loyalty_reward(self, context: dict) -> bool:
        """order_count > 10 AND health_score > 0.8 AND not is_vip"""
        pass
    
    def _random_ab_variant(self) -> str:
        """Return 'A' or 'B' with 50/50 probability"""
        pass
```

**Key Features:**
- 4 campaign types triggered by enrichment signals
- Deterministic templates (Jinja2-rendered)
- A/B variant randomization (stored per campaign)
- Database storage (campaigns table)
- Multi-channel support (email, in_app)

**Tests:**
- Unit: test_health_check_trigger_logic (mock enrichment)
- Unit: test_engagement_trigger_logic
- Unit: test_billing_winback_trigger_logic
- Unit: test_loyalty_reward_trigger_logic
- Unit: test_ab_randomization_distribution (verify 50/50)
- Integration: test_campaign_email_rendering (Jinja2)

**Verify:** `pytest tests/unit/outreach/ -v --tb=short`

#### 2.4 `services/api/src/triage/outreach/ab_test_framework.py`
**Class:** `ABTestFramework`

**Key Methods:**
```python
class ABTestFramework:
    async def record_event(self, campaign_id: int, event_type: str) -> bool:
        """
        Record: 'opened', 'clicked', 'converted'
        Updates campaign.opened_at, .clicked_at, .converted_at
        """
        pass
    
    async def compute_results(self, tenant_id: int, campaign_type: str) -> ABTestResult:
        """
        After min_sample_size (e.g., 100) per variant:
        - open_rate = opened / sent
        - click_rate = clicked / sent
        - conversion_rate = converted / sent
        Returns: ABTestResult with winner (higher conversion_rate)
        """
        pass
```

**Tests:** test_event_recording, test_results_computation_min_sample_size

---

## Batch 3: Escalation Rules, Override, & Handoff (S4.3, S4.5, S4.8)

**Deliverable:** Confidence-based escalation, SLA management, human override, escalation summary + context.

### Dependencies
- S2.1 classification confidence score (from `triage.models.intent.IntentPrediction`)
- S3.1–S3.3 enrichment context
- S3.4 health scoring
- S4.1 anomaly signals
- B1 (anomaly detector)

### Files to Create

#### 3.1 `services/api/src/triage/escalation/__init__.py`
```python
from .rules_engine import EscalationRulesEngine
from .queue_manager import EscalationQueueManager
from .override_handler import OverrideHandler
from .handoff_composer import HandoffComposer
from .models import (
    EscalationRule,
    EscalationJob,
    Priority,
    OverrideReason,
    HandoffContext,
)

__all__ = [
    "EscalationRulesEngine",
    "EscalationQueueManager",
    "OverrideHandler",
    "HandoffComposer",
    "EscalationRule",
    "EscalationJob",
    "Priority",
    "OverrideReason",
    "HandoffContext",
]
```

#### 3.2 `services/api/src/triage/escalation/models.py`
**Classes:**
- `Priority(str, Enum)` — `P0` (15min SLA), `P1` (1hr), `P2` (4hr), `P3` (24hr)
- `EscalationRule(BaseModel)` — fields: rule_id, trigger_type (confidence_low, safety_flag, entity_extraction_fail, anomaly, override_request), priority, description
- `EscalationJob(BaseModel)` — fields: id, tenant_id, ticket_id, priority, deadline, assigned_agent, status (pending, assigned, in_progress, resolved, sla_breached), created_at, escalated_at
- `OverrideReason(BaseModel)` — fields: id, tenant_id, escalation_id, override_by (agent email), reason_text, override_decision (accept/reject), ts
- `HandoffContext(BaseModel)` — fields: escalation_id, summary_text (2–3 sentences), customer_context (health_score, churn_risk, last_3_attempts), quality_score (0–1)

**Tests:** Dataclass serialization, enum validation

#### 3.3 `services/api/src/triage/escalation/rules_engine.py`
**Class:** `EscalationRulesEngine`

**Key Methods:**
```python
class EscalationRulesEngine:
    def __init__(self, db_session):
        # Load escalation rules from database
        # Define trigger conditions
        pass
    
    async def evaluate(self, state: TriageState) -> Optional[EscalationJob]:
        """
        PRIMARY ESCALATION RULE:
        - IF intent_confidence < 0.50 → P1 (1hr SLA)
        
        SECONDARY ESCALATION RULES:
        1. Safety flags (chargeback, legal_threat, etc.) → P0 (15min)
        2. Entity extraction failure (None returned) → P1 (1hr)
        3. Anomaly detected (from S4.1) → determine priority by signal_type:
           - CHURN_SPIKE → P1
           - FRAUD_PATTERN → P0
           - COMPLAINT_SURGE → P1
           - RESPONSE_DELAY → P2
           - VOLUME_SPIKE → P2
           - API_ERROR_RATE → P0
        4. Repeated escalation (ticket_id already escalated 2x) → P0
        
        Returns: EscalationJob (database-inserted) or None if no escalation needed
        """
        pass
    
    async def _check_confidence_rule(self, state: TriageState) -> Tuple[bool, Priority]:
        """Check: intent_confidence < 0.50 → P1"""
        pass
    
    async def _check_safety_flags(self, state: TriageState) -> Tuple[bool, Priority]:
        """Check: any safety_flags present → P0"""
        pass
    
    async def _check_entity_extraction_failure(self, state: TriageState) -> Tuple[bool, Priority]:
        """Check: entities empty or extraction_error present → P1"""
        pass
    
    async def _check_anomaly_signals(self, tenant_id: int) -> Tuple[bool, Priority]:
        """Check anomaly queue, map signal_type to priority"""
        pass
    
    async def _check_repeat_escalation(self, ticket_id: str) -> Tuple[bool, Priority]:
        """Check: ticket escalated >= 2x already → P0"""
        pass
```

**Key Features:**
- Primary rule: confidence < 0.50
- 5 secondary rules with priority mapping
- TriageState integration
- Database insertion

**Tests:**
- Unit: test_confidence_rule_<50 (P1)
- Unit: test_safety_flag_rule_chargeback (P0)
- Unit: test_entity_extraction_failure_rule (P1)
- Unit: test_anomaly_signal_priority_mapping
- Unit: test_repeat_escalation_rule (>=2 escalations → P0)
- Integration: test_evaluate_returns_escalation_job

**Verify:** `pytest tests/unit/escalation/test_rules_engine.py -v --tb=short`

#### 3.4 `services/api/src/triage/escalation/queue_manager.py`
**Class:** `EscalationQueueManager`

**Key Methods:**
```python
class EscalationQueueManager:
    def __init__(self, db_session):
        pass
    
    async def enqueue(self, job: EscalationJob) -> bool:
        """Insert into escalation_queue table + audit trail"""
        pass
    
    async def assign_to_agent(self, job_id: int, agent_id: str) -> bool:
        """Update status=assigned, assigned_agent=agent_id, audit log"""
        pass
    
    async def detect_sla_breaches(self, tenant_id: int) -> List[EscalationJob]:
        """
        Poll every minute (or via background task):
        For each job where status != resolved AND now() > deadline:
        - Set status=sla_breached
        - Emit webhook alert
        - Add +5min auto-escalation to manager
        Returns: List of breached jobs
        """
        pass
    
    async def resolve_job(self, job_id: int, resolution_notes: str) -> bool:
        """Set status=resolved, record resolution_time, audit"""
        pass
    
    async def get_queue_stats(self, tenant_id: int) -> dict:
        """
        Returns: {
            pending_count, assigned_count, overdue_count,
            avg_wait_time, p95_wait_time, sla_breach_pct
        }
        """
        pass
```

**Key Features:**
- SLA deadline calculation (P0=15min, P1=1hr, P2=4hr, P3=24hr)
- +5min auto-escalation at SLA breach
- Audit trail logging
- Queue statistics

**Tests:**
- Unit: test_enqueue_job_creates_record
- Unit: test_assign_to_agent_updates_status
- Integration: test_detect_sla_breaches_marks_overdue
- Integration: test_auto_escalation_to_manager (+5min)
- Integration: test_resolve_job_records_resolution_time

**Verify:** `pytest tests/unit/escalation/test_queue_manager.py -v --tb=short`

#### 3.5 `services/api/src/triage/escalation/override_handler.py`
**Class:** `OverrideHandler`

**Key Methods:**
```python
class OverrideHandler:
    async def record_override(
        self,
        escalation_id: int,
        override_by: str,  # agent email
        reason_text: str,
        override_decision: str,  # 'accept' or 'reject'
    ) -> OverrideReason:
        """
        Record human override with reason.
        Insert into override_reason table.
        Route feedback to S4.7 (feedback loop).
        Returns: OverrideReason record
        """
        pass
    
    async def get_override_reasons(self, tenant_id: int, limit: int = 100) -> List[OverrideReason]:
        """Fetch recent overrides for feedback analysis"""
        pass
```

**Tests:**
- Unit: test_override_recording_stores_reason
- Integration: test_override_feedback_routing

**Verify:** `pytest tests/unit/escalation/test_override_handler.py -v --tb=short`

#### 3.6 `services/api/src/triage/escalation/handoff_composer.py`
**Class:** `HandoffComposer`

**Key Methods:**
```python
class HandoffComposer:
    async def compose_handoff(
        self,
        escalation_id: int,
        state: TriageState,
        enrichment_context: dict,
        escalation_job: EscalationJob,
    ) -> HandoffContext:
        """
        Compose escalation summary and context for human agent:
        
        1. Summary (2–3 sentences):
           - Primary issue from intent + entities
           - Key enrichment signal (VIP? At risk? Recent spike?)
           - Example: "Customer is VIP with $2K spend. Order status query escalated due to low confidence (0.42) on classification."
        
        2. Customer Context:
           - health_score, churn_risk_level
           - is_vip, account_age_days
           - last_3_attempts (timestamps + intent)
        
        3. Quality Scorer:
           - Evaluate summary completeness (target >90%)
           - Check presence of key fields
           - Returns: quality_score (0–1)
        
        Insert into context_handoff table.
        Return: HandoffContext with all fields populated
        """
        pass
    
    def _extract_summary(
        self,
        state: TriageState,
        enrichment_context: dict,
        escalation_reason: str,
    ) -> str:
        """Generate 2–3 sentence handoff summary"""
        pass
    
    def _extract_customer_context(self, enrichment_context: dict, state: TriageState) -> dict:
        """Extract health_score, churn_risk, is_vip, last_3_attempts"""
        pass
    
    def _compute_quality_score(self, handoff: dict) -> float:
        """
        Checklist (8 items, each worth 0.125):
        ✓ summary not empty
        ✓ summary >= 50 chars
        ✓ health_score present
        ✓ churn_risk present
        ✓ last_3_attempts not empty
        ✓ customer_context includes is_vip
        ✓ escalation_reason present
        ✓ created_at recent
        
        Score = 1.0 - (missing_items / 8)
        """
        pass
```

**Key Features:**
- Deterministic summary generation
- Context extraction from enrichment + TriageState
- Quality scoring (target >90%)
- Database storage

**Tests:**
- Unit: test_summary_generation_deterministic
- Unit: test_context_extraction_all_fields
- Unit: test_quality_score_computation
- Integration: test_compose_handoff_complete

**Verify:** `pytest tests/unit/escalation/test_handoff_composer.py -v --tb=short`

---

## Batch 4: Multi-Channel Escalation Routing (S4.6)

**Deliverable:** Slack/email/PagerDuty/webhook dispatcher + on-call rotation sync + DND scheduling.

### Dependencies
- B3 (escalation queue manager)
- External services: Slack, PagerDuty, SendGrid (or native email)

### Files to Create

#### 4.1 `services/api/src/triage/escalation/router.py`
**Class:** `EscalationRouter`

**Key Methods:**
```python
class EscalationRouter:
    def __init__(self, slack_client, pagerduty_client, email_service, webhook_dispatcher):
        self.slack = slack_client
        self.pagerduty = pagerduty_client
        self.email = email_service
        self.webhook = webhook_dispatcher
    
    async def route_escalation(
        self,
        job: EscalationJob,
        handoff_context: HandoffContext,
        escalation_job_id: int,
    ) -> dict:
        """
        Multi-channel routing with DND + fallback:
        
        1. Load on-call rotation from PagerDuty (hourly cache, 1hr TTL)
        2. Check on-call agent's DND schedule
        3. If DND active: try next on-call, or fallback to email queue
        4. Send via all enabled channels:
           - Slack DM to on-call agent (if enabled, not DND)
           - PagerDuty incident + escalation policy
           - Email to escalation queue (backup)
           - Webhook POST to external system (if configured)
        
        Returns: {
            routed_to_channels: ['slack', 'pagerduty', 'email'],
            on_call_agent: 'agent@example.com',
            routing_timestamp: datetime,
            success: bool
        }
        """
        pass
    
    async def _sync_oncall_rotation(self, tenant_id: int) -> dict:
        """
        Fetch from PagerDuty every hour (cached):
        Returns: {
            on_call_schedule_id: 'SCHEDULE_ID',
            current_oncall: {'id': 'PID123', 'email': 'agent@example.com', 'name': 'Agent Name'},
            next_oncall: {...},
            schedule_start: datetime,
            schedule_end: datetime,
        }
        """
        pass
    
    async def _check_dnd_schedule(self, agent_email: str) -> bool:
        """
        Query dnd_schedules table for agent.
        Check if current_time falls within [start_time, end_time).
        Returns: True if DND active, False otherwise.
        """
        pass
    
    async def _send_slack(self, agent_email: str, job: EscalationJob, handoff: HandoffContext) -> bool:
        """
        Send Slack DM:
        Channel: @agent_email (look up Slack ID from DB mapping)
        Message format:
        ```
        🔴 P[0-3] Escalation: {ticket_id}
        {handoff_context.summary_text}
        Deadline: {job.deadline}
        [View in Dashboard]
        ```
        """
        pass
    
    async def _send_pagerduty(self, job: EscalationJob, handoff: HandoffContext) -> bool:
        """
        Create PagerDuty incident via escalation policy.
        Title: f"P{priority} Escalation: {ticket_id}"
        Description: handoff_context.summary_text
        Urgency: high (P0-P1) or low (P2-P3)
        """
        pass
    
    async def _send_email(self, job: EscalationJob, handoff: HandoffContext) -> bool:
        """
        Send email to escalation_queue@tenant.example.com
        Subject: f"[P{priority}] {ticket_id}: {primary_intent}"
        Body: HTML template with handoff summary + links
        """
        pass
    
    async def _send_webhook(self, job: EscalationJob, handoff: HandoffContext) -> bool:
        """
        POST to configured webhook URL with:
        {
            escalation_id, tenant_id, ticket_id,
            priority, deadline, summary, customer_context
        }
        """
        pass
```

**Key Features:**
- 4-channel routing (Slack, PagerDuty, email, webhook)
- On-call rotation sync from PagerDuty (1hr cache)
- DND (Do Not Disturb) scheduling
- Fallback chain (Slack → PagerDuty → email)
- Metrics logging (route_channel, success_rate)

**Configuration (env vars):**
```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_AGENT_ID_MAPPING={"agent@example.com": "U12345678"}  # JSON string

PAGERDUTY_API_TOKEN=u+...
PAGERDUTY_ESCALATION_POLICY_ID=P12345
PAGERDUTY_SERVICE_ID=P67890
PAGERDUTY_ONCALL_SYNC_INTERVAL_HOURS=1

SENDGRID_API_KEY=SG.xxx
ESCALATION_QUEUE_EMAIL=triage-escalation@example.com

ESCALATION_WEBHOOK_URL=https://external-system.example.com/escalations
ESCALATION_WEBHOOK_SECRET=webhook_secret_for_hmac
```

**Tests:**
- Unit: test_oncall_sync_parses_pagerduty_response
- Unit: test_dnd_check_returns_true_when_active
- Unit: test_routing_prefers_oncall_not_dnd
- Integration: test_send_slack_formats_message
- Integration: test_send_pagerduty_creates_incident
- Integration: test_send_email_with_html_template
- Integration: test_send_webhook_with_hmac_signature
- Integration: test_fallback_chain_skips_dnd

**Verify:** `pytest tests/unit/escalation/test_router.py -v --tb=short`

---

## Batch 5: Monitoring, Alerting & Operations Dashboard (S4.4, S4.9)

**Deliverable:** WebSocket dashboard + Prometheus metrics + Grafana + AlertManager rules.

### Dependencies
- Sprint 3 analytics dashboards (S3.9)
- S4.1 anomaly detector
- B3 escalation queue

### Files to Create

#### 5.1 `services/api/src/triage/monitoring/__init__.py`
```python
from .metrics_collector import MetricsCollector
from .dashboard_server import DashboardServer
from .models import KPIMetric, DashboardPanel

__all__ = ["MetricsCollector", "DashboardServer", "KPIMetric", "DashboardPanel"]
```

#### 5.2 `services/api/src/triage/monitoring/models.py`
**Classes:**
- `KPIMetric(BaseModel)` — fields: metric_name, value, unit, timestamp, threshold_warning, threshold_critical
- `DashboardPanel(BaseModel)` — fields: panel_id, title, panel_type (kpi_card, time_series, gauge, anomaly_timeline), data, refreshed_at

**Tests:** Dataclass serialization

#### 5.3 `services/api/src/triage/monitoring/metrics_collector.py`
**Class:** `MetricsCollector`

**Key Methods:**
```python
class MetricsCollector:
    """Prometheus metric collection for S4.9."""
    
    def __init__(self):
        # Initialize Prometheus counters, gauges, histograms
        self.escalation_rate = Counter(
            'escalation_rate', 'Escalations per minute', ['tenant_id']
        )
        self.resolution_time = Histogram(
            'resolution_time_seconds', 'Time to resolve', ['autonomy_level']
        )
        self.cost_per_resolution = Gauge(
            'cost_per_resolution_usd', 'Cost per resolved ticket', ['tenant_id']
        )
        self.sla_breach_count = Counter(
            'sla_breach_count', 'SLA breaches', ['priority', 'tenant_id']
        )
        self.anomaly_detection_latency = Histogram(
            'anomaly_detection_latency_ms', 'Anomaly detection time', ['signal_type']
        )
        self.escalation_routing_latency = Histogram(
            'escalation_routing_latency_ms', 'Routing time', ['channel']
        )
        self.context_quality_score = Gauge(
            'context_quality_score', 'Handoff context quality', ['tenant_id']
        )
    
    async def record_escalation(self, tenant_id: str, priority: str) -> None:
        """Increment escalation_rate, sla_breach_count counters"""
        pass
    
    async def record_resolution(self, resolution_time_ms: float, autonomy_level: int) -> None:
        """Record resolution_time histogram"""
        pass
    
    async def record_cost(self, tenant_id: str, cost_usd: float) -> None:
        """Update cost_per_resolution gauge"""
        pass
    
    async def record_anomaly_detection(self, signal_type: str, latency_ms: float) -> None:
        """Record anomaly_detection_latency histogram"""
        pass
    
    async def record_routing(self, channel: str, latency_ms: float) -> None:
        """Record routing latency by channel"""
        pass
    
    async def record_context_quality(self, tenant_id: str, quality_score: float) -> None:
        """Update context_quality_score gauge"""
        pass
```

**Key Metrics:**
- escalation_rate (counter, per tenant)
- resolution_time (histogram, per autonomy_level)
- cost_per_resolution (gauge, per tenant)
- sla_breach_count (counter, per priority)
- anomaly_detection_latency (histogram, per signal_type)
- escalation_routing_latency (histogram, per channel)
- context_quality_score (gauge, per tenant)

**Tests:**
- Unit: test_record_escalation_increments_counter
- Unit: test_record_resolution_records_histogram
- Unit: test_record_cost_updates_gauge

**Verify:** `pytest tests/unit/monitoring/test_metrics_collector.py -v --tb=short`

#### 5.4 `services/api/src/triage/monitoring/dashboard_server.py`
**Class:** `DashboardServer`

**Key Methods:**
```python
class DashboardServer:
    """WebSocket dashboard server for real-time monitoring (S4.4)."""
    
    def __init__(self, db_session, anomaly_detector, queue_manager, metrics_collector):
        self.db = db_session
        self.detector = anomaly_detector
        self.queue = queue_manager
        self.metrics = metrics_collector
    
    async def get_dashboard_data(self, tenant_id: int) -> dict:
        """
        Returns 4-panel dashboard:
        
        1. AGENT_PERFORMANCE panel:
           - Metrics: escalation_pct, avg_resolution_time, csat
           - Data from v_agent_performance_daily
           - Current day vs 7-day average
        
        2. ANOMALY_ALERTS panel:
           - Recent anomalies from AnomalyDetector.detect_signals()
           - Anomaly type, severity (sigma deviation), timestamp
           - Timeline view (last 24h)
        
        3. OVERRIDE_QUEUE panel:
           - Recent override_reason records
           - Agent, reason, decision (accept/reject)
           - Count pending review
        
        4. WORKLOAD_BALANCING panel:
           - Queue depth (pending escalations)
           - On-call agent utilization
           - SLA breach forecast (escalations approaching deadline)
        
        Returns: {
            agent_performance: {...},
            anomaly_alerts: [...],
            override_queue: [...],
            workload_balancing: {...},
            refreshed_at: datetime,
        }
        """
        pass
    
    async def stream_updates(self, tenant_id: int, websocket) -> None:
        """
        WebSocket stream: send dashboard updates every 5 seconds.
        Format: {type: 'dashboard_update', data: {...}, timestamp: datetime}
        """
        pass
```

**Key Features:**
- 4-panel real-time dashboard
- WebSocket streaming (5s refresh)
- KPI cards (escalation rate, avg resolution time, CSAT)
- Anomaly timeline (24h)
- Override queue status
- Workload balancing alerts

**API Endpoint:** `GET /api/v1/dashboard/{tenant_id}` → returns dashboard data  
**WebSocket Endpoint:** `WS /ws/dashboard/{tenant_id}` → streams updates

**Tests:**
- Unit: test_get_dashboard_data_returns_4_panels
- Unit: test_dashboard_data_contains_required_fields
- Integration: test_websocket_stream_sends_updates

**Verify:** `pytest tests/unit/monitoring/test_dashboard_server.py -v --tb=short`

#### 5.5 Configuration Files

##### `config/prometheus/prometheus.yml`
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'triage-agent'
    static_configs:
      - targets: ['localhost:8000']  # FastAPI Prometheus /metrics endpoint
    metrics_path: '/metrics'

  - job_name: 'postgresql'
    static_configs:
      - targets: ['localhost:9187']  # postgres_exporter

  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:9121']  # redis_exporter
```

##### `config/alertmanager/alertmanager.yml`
```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'triage-escalation'
  group_by: ['alertname', 'tenant_id']
  group_wait: 10s
  group_interval: 30s
  repeat_interval: 4h

receivers:
  - name: 'triage-escalation'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#escalation-alerts'
        title_link: 'https://dashboard.example.com/alerts'
        icon_emoji: ':warning:'
```

##### `config/alertmanager/alert-rules.yml`
```yaml
groups:
  - name: triage_alerts
    interval: 1m
    rules:
      # Alert: SLA breach rate > 5%
      - alert: HighSLABreachRate
        expr: (increase(sla_breach_count[5m]) / increase(escalation_rate[5m])) > 0.05
        for: 5m
        annotations:
          summary: "SLA breach rate > 5% for tenant {{ $labels.tenant_id }}"
      
      # Alert: Anomaly detection latency > 2s
      - alert: SlowAnomalyDetection
        expr: histogram_quantile(0.99, anomaly_detection_latency_ms) > 2000
        for: 5m
        annotations:
          summary: "Anomaly detection p99 > 2s"
      
      # Alert: Escalation queue depth > 50
      - alert: LargeEscalationQueue
        expr: escalation_queue_depth > 50
        for: 5m
        annotations:
          summary: "Escalation queue depth > 50"
      
      # Alert: Context quality score < 0.85
      - alert: LowContextQuality
        expr: context_quality_score < 0.85
        for: 10m
        annotations:
          summary: "Context handoff quality score < 85%"
```

##### `config/grafana/dashboard-sprint4.json`
Four pre-built Grafana dashboard JSONs:

1. **Agent Performance Dashboard**
   - Panels: escalation_rate (counter), resolution_time (histogram p50/p95/p99), CSAT (gauge)
   - Filters: tenant_id, date_range
   
2. **Anomaly Alerts Dashboard**
   - Panels: anomaly timeline (24h), anomaly count by type, detection latency
   - Threshold lines for sigma deviations
   
3. **SLA & Queue Dashboard**
   - Panels: queue depth (time series), SLA breach rate (gauge), priority distribution
   - Forecast panel (escalations approaching deadline in next 1h)
   
4. **Operations Overview**
   - Single-page summary: escalation_rate, resolution_time p95, sla_breach_pct, anomaly_count
   - KPI cards, status indicators

**Verify:** `pytest tests/unit/monitoring/test_dashboard_server.py -v --tb=short`

---

## Batch 6: Feedback Loop Extension & Acceptance Gate (S4.7, S4.10)

**Deliverable:** Extend feedback module with signal routing, E2E scenarios, golden set, performance benchmarks.

### Dependencies
- S3.8 existing feedback module (feedback_ingester.py, learning_loop.py)
- B1 anomaly detector
- B3 escalation rules + override handler
- B5 metrics collector

### Files to Create

#### 6.1 `services/api/src/triage/feedback/signal_router.py`
**Class:** `SignalRouter`

**Key Methods:**
```python
class SignalRouter:
    """S4.7: Route feedback signals to improvement loops."""
    
    async def route_feedback_signal(self, signal: dict) -> bool:
        """
        Route override reasons to appropriate improvement modules:
        
        signal = {
            tenant_id, escalation_id, override_by,
            reason_text, override_decision,
            primary_intent, intent_confidence
        }
        
        Routes:
        1. If reason contains 'confidence' or 'uncertain':
           → Send to S3.6 (sentiment analyzer) for retraining signal
        2. If reason contains 'churn' or 'risk':
           → Send to S3.4 (health scorer) for retraining signal
        3. If reason contains 'missing knowledge' or 'KB':
           → Send to S3.5 (knowledge gap analyzer) for gap report
        4. If reason contains 'entity extraction':
           → Send to S2.4 (entity extractor) for pattern analysis
        5. Else:
           → Route to generic learning_loop for EWMA drift tracking
        
        Returns: success flag
        """
        pass
    
    async def _ingest_to_sentiment_retraining(self, signal: dict) -> bool:
        """Insert into sentiment_feedback_queue for retraining"""
        pass
    
    async def _ingest_to_health_score_retraining(self, signal: dict) -> bool:
        """Insert into health_score_feedback_queue for retraining"""
        pass
    
    async def _ingest_to_knowledge_gap_analysis(self, signal: dict) -> bool:
        """Insert into knowledge_gap_feedback_queue for KB expansion"""
        pass
    
    async def _ingest_to_entity_extraction_pattern(self, signal: dict) -> bool:
        """Insert into entity_extraction_feedback_queue"""
        pass
```

**Tests:**
- Unit: test_route_confidence_feedback_to_sentiment
- Unit: test_route_churn_feedback_to_health_score
- Unit: test_route_kb_feedback_to_knowledge_gap
- Integration: test_signal_routing_end_to_end

**Verify:** `pytest tests/unit/feedback/test_signal_router.py -v --tb=short`

#### 6.2 `tests/acceptance/test_s4_scenarios.py`

**Test Class:** `TestS4AcceptanceScenarios`

**Key Scenarios (6 E2E):**

```python
@pytest.mark.acceptance
class TestS4AcceptanceScenarios:
    """
    E2E scenarios testing Sprint 4 proactive triggers & escalation.
    """
    
    async def test_s4_e1_churn_escalation(self, db_session, anomaly_detector, rules_engine, router):
        """
        E1: Churn Spike → Anomaly Detection → Escalation → Multi-Channel Routing
        
        Given: Customer health_score drops from 0.8 to 0.3 (EWMA spike)
        When: AnomalyDetector.detect_signals() runs
        Then:
            1. Detects CHURN_SPIKE signal with confidence > 0.9
            2. EscalationRulesEngine.evaluate() returns EscalationJob (P1)
            3. EscalationRouter.route_escalation() sends to Slack + PagerDuty
            4. Dashboard anomaly_alerts panel shows signal
        
        Assertions:
            - Signal type = CHURN_SPIKE
            - Job priority = P1 (1hr SLA)
            - Routed to >=2 channels
            - Quality score > 0.9
        """
        pass
    
    async def test_s4_e2_fraud_override(self, db_session, rules_engine, override_handler):
        """
        E2: Fraud Pattern + Manual Override → Feedback Loop
        
        Given: Multiple chargeback flags + high-value order spike
        When: Agent reviews and accepts escalation (fraud confirmed)
        Then:
            1. Override recorded with reason 'fraud_confirmed'
            2. SignalRouter routes to entity extraction pattern analysis
            3. Feedback ingester logs override for retraining
            4. Health scorer adjusts churn_risk features
        
        Assertions:
            - Override reason captured
            - Feedback routed to correct module
            - Learning loop ingest succeeds
        """
        pass
    
    async def test_s4_e3_low_confidence_escalation(self, db_session, rules_engine, queue_manager):
        """
        E3: Low Confidence Escalation (Primary Rule)
        
        Given: Intent classification confidence = 0.42
        When: EscalationRulesEngine.evaluate() runs
        Then:
            1. PRIMARY rule triggers (confidence < 0.50)
            2. EscalationJob created with P1 priority
            3. Job enqueued to escalation_queue
            4. Audit trail logged
        
        Assertions:
            - Job priority = P1
            - Job status = pending
            - Audit record exists
        """
        pass
    
    async def test_s4_e4_sla_breach_auto_escalation(self, db_session, queue_manager, router):
        """
        E4: SLA Breach → Auto-Escalation to Manager
        
        Given: P1 job created 65 minutes ago (SLA deadline 1hr)
        When: detect_sla_breaches() runs
        Then:
            1. Job marked status=sla_breached
            2. Auto-escalation created with +5min deadline
            3. Manager notified via Slack + email
            4. Dashboard workload_balancing shows forecast
        
        Assertions:
            - Job status = sla_breached
            - New escalation created with corrected deadline
            - Notification channels > 0
        """
        pass
    
    async def test_s4_e5_multichannel_dnd_fallback(self, db_session, router):
        """
        E5: Multi-Channel Routing with DND + Fallback
        
        Given: Primary on-call agent has DND active (8am-5pm, currently 10am)
        When: EscalationRouter.route_escalation() runs
        Then:
            1. Check DND schedule returns True
            2. Fallback to secondary on-call agent
            3. Slack sent to secondary agent
            4. PagerDuty escalation policy triggered
            5. Email sent to escalation_queue (backup)
        
        Assertions:
            - DND check passed
            - Routed to secondary agent
            - Channels list includes email (fallback)
        """
        pass
    
    async def test_s4_e6_proactive_campaign_tracking(self, db_session, campaign_engine, ab_test_framework):
        """
        E6: Proactive Campaign → A/B Test Tracking → Winner Decision
        
        Given: 150 customers in HEALTH_CHECK campaign (75 variant A, 75 variant B)
        When: After 7 days, compute_results() runs
        Then:
            1. Variant A: open_rate=0.35, click_rate=0.12, conversion_rate=0.05
            2. Variant B: open_rate=0.38, click_rate=0.14, conversion_rate=0.062
            3. Winner = Variant B (higher conversion)
            4. Dashboard KPI shows campaign effectiveness
        
        Assertions:
            - A/B results computed correctly
            - Winner identified
            - Metrics logged
        """
        pass
```

**Tests:** 6 E2E scenarios using pytest-asyncio + mocks

**Verify:** `pytest tests/acceptance/test_s4_scenarios.py -v --tb=short`

#### 6.3 `tests/golden_sets/s4_golden_set.json`

**Golden Dataset:** 25 pre-curated records with expected outcomes

```json
[
  {
    "id": "G4-001",
    "scenario": "Churn spike detected",
    "customer_id": 1001,
    "health_score": 0.28,
    "sentiment_trend": "declining",
    "order_frequency": "low",
    "expected_anomaly_type": "CHURN_SPIKE",
    "expected_escalation_priority": "P1",
    "expected_channels": ["slack", "pagerduty", "email"],
    "expected_handoff_quality_score": 0.92,
    "assertions": {
      "anomaly_detected": true,
      "escalation_created": true,
      "routing_success": true
    }
  },
  {
    "id": "G4-002",
    "scenario": "Fraud pattern with chargeback",
    "customer_id": 1002,
    "chargeback_count": 3,
    "high_value_orders": 5,
    "expected_anomaly_type": "FRAUD_PATTERN",
    "expected_escalation_priority": "P0",
    "expected_override_decision": "accept",
    "assertions": {
      "anomaly_confidence": {"min": 0.8, "max": 1.0},
      "priority": "P0"
    }
  },
  ...
]
```

**Script:** `pytest tests/golden_sets/s4_golden_set.py -v` → validates 25 records

**Verify:** `pytest tests/golden_sets/s4_golden_set.py -v --tb=short`

#### 6.4 Performance Benchmarks (integrated into acceptance test)

```python
@pytest.mark.performance
class TestS4PerformanceBenchmarks:
    """Performance gates for Sprint 4."""
    
    async def test_anomaly_detection_latency_<2s(self, anomaly_detector, db_session):
        """Anomaly detection must complete in <2s p99"""
        # Generate 10K+ daily metrics
        # Run detect_signals() 100 times
        # Assert p99 latency < 2000ms
        pass
    
    async def test_escalation_creation_latency_<5s(self, rules_engine, queue_manager):
        """Escalation job creation + queueing must be <5s p99"""
        # Create 1K TriageState objects
        # Call rules_engine.evaluate() for each
        # Assert p99 latency < 5000ms
        pass
    
    async def test_escalation_routing_latency_<3s(self, router):
        """Routing to all channels must be <3s p99"""
        # Call route_escalation() 100 times
        # Measure latency per channel
        # Assert p99 overall < 3000ms
        pass
    
    async def test_context_quality_score_>90(self, handoff_composer):
        """Context handoff quality must average >90%"""
        # Compose 100 handoffs with varied inputs
        # Assert mean quality_score > 0.90
        pass
```

**Verify:** `pytest tests/acceptance/test_s4_scenarios.py::TestS4PerformanceBenchmarks -v`

---

## Database Migrations

**File:** `packages/py_core/alembic/versions/0007_sprint4_escalation_tables.py`

**Migration:** Creates 5 new tables

```sql
-- Escalation Queue (S4.3, S4.5)
CREATE TABLE triage.escalation_queue (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ticket_id VARCHAR(255) NOT NULL,
    priority VARCHAR(10) NOT NULL CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    deadline TIMESTAMPTZ NOT NULL,
    assigned_agent VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'assigned', 'in_progress', 'resolved', 'sla_breached')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, ticket_id)
);

-- Escalation Audit Trail
CREATE TABLE triage.escalation_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    escalation_id BIGINT NOT NULL REFERENCES escalation_queue(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,  -- 'created', 'assigned', 'resolved', 'sla_breached'
    actor VARCHAR(255) NOT NULL,  -- agent email or 'system'
    reason VARCHAR(512),
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    INDEX idx_escalation_audit_tenant_ts (tenant_id, ts DESC)
);

-- Override Reason (S4.3)
CREATE TABLE triage.override_reason (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    escalation_id BIGINT NOT NULL REFERENCES escalation_queue(id) ON DELETE CASCADE,
    override_by VARCHAR(255) NOT NULL,  -- agent email
    reason_text TEXT NOT NULL,
    override_decision VARCHAR(20) NOT NULL CHECK (override_decision IN ('accept', 'reject')),
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Feedback Signals (S4.7)
CREATE TABLE triage.feedback_signals (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id VARCHAR(255) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,  -- 'override_reason', 'churn', 'fraud', 'kb_gap'
    payload JSONB NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    INDEX idx_feedback_signals_tenant_ts (tenant_id, ts DESC)
);

-- Context Handoff (S4.8)
CREATE TABLE triage.context_handoff (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    escalation_id BIGINT NOT NULL REFERENCES escalation_queue(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    quality_score NUMERIC(3, 2) NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    context_json JSONB NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- DND Schedule (S4.6)
CREATE TABLE triage.dnd_schedules (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_email VARCHAR(255) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_time > start_time)
);

-- OnCall Cache (S4.6, synced hourly from PagerDuty)
CREATE TABLE triage.oncall_rotation_cache (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    schedule_id VARCHAR(255) NOT NULL,
    current_oncall_email VARCHAR(255) NOT NULL,
    next_oncall_email VARCHAR(255),
    schedule_start TIMESTAMPTZ NOT NULL,
    schedule_end TIMESTAMPTZ NOT NULL,
    last_synced TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, schedule_id)
);

-- Campaigns (S4.2)
CREATE TABLE triage.campaigns (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255) NOT NULL,
    template_id VARCHAR(255) NOT NULL,
    campaign_type VARCHAR(50) NOT NULL,  -- 'health_check', 'engagement', 'billing_winback', 'loyalty_reward'
    variant CHAR(1) NOT NULL CHECK (variant IN ('A', 'B')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    INDEX idx_campaigns_tenant_type (tenant_id, campaign_type)
);
```

**Verify:** `alembic upgrade head` — all tables created

---

## Environment Variables (Added to .env.example)

```bash
# ========== S4.1: ANOMALY DETECTION ==========
ANOMALY_EWMA_ALPHA=0.1
ANOMALY_ISOLATION_FOREST_CONTAMINATION=0.05
ANOMALY_WEBHOOK_URL=http://localhost:8000/api/v1/escalation/enqueue
ANOMALY_DETECTION_ENABLED=true

# ========== S4.2: PROACTIVE OUTREACH ==========
CAMPAIGN_TEMPLATES_PATH=/config/campaigns/
CAMPAIGN_AB_TEST_MIN_SAMPLE_SIZE=100
CAMPAIGN_ENABLED=true

# ========== S4.3, S4.5, S4.8: ESCALATION ==========
ESCALATION_PRIMARY_CONFIDENCE_THRESHOLD=0.50
ESCALATION_SLA_P0_MINUTES=15
ESCALATION_SLA_P1_MINUTES=60
ESCALATION_SLA_P2_MINUTES=240
ESCALATION_SLA_P3_MINUTES=1440
ESCALATION_AUTO_ESCALATION_TO_MANAGER_MINUTES=5
ESCALATION_QUEUE_ENABLED=true

# ========== S4.4, S4.9: MONITORING ==========
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
GRAFANA_ENABLED=true
GRAFANA_PORT=3000
ALERTMANAGER_ENABLED=true
ALERTMANAGER_PORT=9093

# ========== S4.6: MULTI-CHANNEL ROUTING ==========
SLACK_BOT_TOKEN=xoxb-
SLACK_AGENT_ID_MAPPING={}

PAGERDUTY_API_TOKEN=u+
PAGERDUTY_ESCALATION_POLICY_ID=
PAGERDUTY_SERVICE_ID=
PAGERDUTY_ONCALL_SYNC_INTERVAL_HOURS=1

SENDGRID_API_KEY=SG.
ESCALATION_QUEUE_EMAIL=

ESCALATION_WEBHOOK_URL=
ESCALATION_WEBHOOK_SECRET=

# ========== S4.7: FEEDBACK LOOP ROUTING ==========
FEEDBACK_SIGNAL_ROUTING_ENABLED=true

# ========== S4.10: ACCEPTANCE GATE ==========
GOLDEN_SET_PATH=/tests/golden_sets/
PERFORMANCE_BENCHMARK_ENABLED=true
```

---

## Test Summary

### Unit Tests (35+)

| Module | Test File | Count | Scenarios |
|--------|-----------|-------|-----------|
| Anomaly | test_detector.py | 5 | EWMA, Isolation Forest, all 6 signal types, webhook |
| Outreach | test_campaign_engine.py | 6 | All 4 campaign triggers, A/B randomization |
| Outreach | test_ab_test_framework.py | 2 | Event recording, results computation |
| Escalation | test_rules_engine.py | 6 | All 5 escalation rules (confidence, safety, entity, anomaly, repeat) |
| Escalation | test_queue_manager.py | 5 | Enqueue, assign, SLA breach, resolve, stats |
| Escalation | test_override_handler.py | 2 | Record override, fetch reasons |
| Escalation | test_handoff_composer.py | 4 | Summary generation, context extraction, quality score |
| Escalation | test_router.py | 8 | OnCall sync, DND check, all 4 channels, fallback chain |
| Monitoring | test_metrics_collector.py | 3 | Record escalation, resolution, cost |
| Monitoring | test_dashboard_server.py | 3 | Dashboard data, 4 panels, WebSocket stream |
| Feedback | test_signal_router.py | 4 | Route to sentiment, health score, knowledge gap, entity extraction |

**Total Unit Tests:** 48

### Acceptance Tests (6 E2E)
- E1: Churn escalation
- E2: Fraud override
- E3: Low confidence escalation
- E4: SLA breach auto-escalation
- E5: Multi-channel DND fallback
- E6: Proactive campaign tracking

### Performance Benchmarks (4)
- Anomaly detection <2s p99
- Escalation creation <5s p99
- Escalation routing <3s p99
- Context quality >90% average

### Golden Set
- 25 records covering all scenarios
- Validates end-to-end flow

**Total Tests:** 48 unit + 6 E2E + 4 perf + 25 golden = **83 test cases**

---

## Implementation Order & Dependencies

**Phase 1: Foundation (Batches 1, 2)**
1. B1: Anomaly Detection (S4.1) — 2 files
2. B2: Proactive Outreach (S4.2) — 3 files

**Phase 2: Core Escalation (Batch 3)**
3. B3: Escalation Rules, Override, Handoff (S4.3, S4.5, S4.8) — 5 files

**Phase 3: Routing & Monitoring (Batches 4, 5)**
4. B4: Multi-Channel Routing (S4.6) — 1 file
5. B5: Monitoring & Alerting (S4.4, S4.9) — 3 config files + 3 Python files

**Phase 4: Integration & Tests (Batch 6)**
6. B6: Feedback Loop & Acceptance (S4.7, S4.10) — 2 files + tests + golden set

**Phase 5: Database & Deployment**
7. Alembic migration (0007_sprint4_escalation_tables.py)
8. Environment variables (.env.example)

---

## Risk Register & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| PagerDuty API rate limits | Medium | Medium | Implement 1hr cache for on-call rotation |
| Slack webhook latency | Low | Low | Async send, timeout + fallback to email |
| EWMA stale data | Medium | Low | Query only recent materialized view data (7-day lookback) |
| Isolation Forest overfitting | Low | Medium | Contamination parameter tuning (0.05), cross-validation in offline process |
| SLA breach false positives | Low | High | Validate deadline calculation in unit tests, add 5min grace period |
| Context handoff completeness | Medium | Medium | Quality score gate (>0.9), manual review for <0.85 scores |
| Webhook signature collision | Very Low | High | Use HMAC-SHA256, store secrets in environment, rotate quarterly |
| Database migration rollback | Low | High | Test migration on staging, have down() implementation |

---

## Success Criteria (Definition of Done)

For Sprint 4 to be complete:

✅ All 19 Python files created and pass linting (ruff, mypy --strict)  
✅ 48+ unit tests passing with ≥80% coverage per module  
✅ 6 E2E acceptance scenarios passing  
✅ 4 performance benchmarks met (<2s, <5s, <3s, >90%)  
✅ 25-record golden set validated  
✅ Alembic migration runs successfully (up and down)  
✅ All 10 deliverables (S4.1–S4.10) implemented and integrated  
✅ Environment variables documented  
✅ Prometheus + Grafana + AlertManager config deployed  
✅ Code review approved  
✅ GitHub Actions CI passes  

---

## Files Summary

| Category | Count | Files |
|----------|-------|-------|
| Python Modules | 19 | anomaly/ (2), outreach/ (3), escalation/ (5), monitoring/ (3), feedback/ (1), tests (5) |
| Config Files | 3 | prometheus.yml, alertmanager.yml, alert-rules.yml |
| Grafana Dashboards | 1 | dashboard-sprint4.json |
| Alembic Migrations | 1 | 0007_sprint4_escalation_tables.py |
| Test Files | 2 | test_s4_scenarios.py, s4_golden_set.py |
| Environment | 1 | .env.example (append) |
| **Total** | **27** | |

---

## Next Steps After Sprint 4

1. **LangGraph Integration:** Wire S4 modules into existing LangGraph triage graph
2. **UI Dashboard:** Build React/Vue frontend for operations dashboard + WebSocket client
3. **Performance Tuning:** Benchmark at scale (10K+ daily signals), optimize queries
4. **Production Rollout:** Blue-green deployment, canary rollout to 10% → 50% → 100% customers
5. **Sprint 5:** Advanced features (predictive SLA, multi-tenant threshold tuning, ML-based routing)

---

**Document Version:** 1.0  
**Created:** January 2026  
**Status:** READY FOR IMPLEMENTATION
