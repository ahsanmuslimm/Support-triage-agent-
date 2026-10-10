# SPRINT 4 OVERVIEW — Proactive Triggers & Escalation

**Sprint:** 4  
**Total Deliverables:** 10 items (S4.1–S4.10)  
**Lines of Specification:** ~8,100 lines  
**Dependencies:** Sprints 0–3 (foundation, ingestion, classification, enrichment)  
**Status:** COMPLETE & READY FOR IMPLEMENTATION

---

## Executive Summary

Sprint 4 transforms the support triage platform from **reactive** (respond to incoming tickets) to **proactive** (detect issues, escalate intelligently, continuously improve). Key capabilities:

- **Anomaly Detection** (S4.1): Real-time signals (churn spike, fraud, complaints, bot activity)
- **Proactive Outreach** (S4.2): Health-triggered campaigns (email, in-app) with A/B testing
- **Escalation & Override** (S4.3): Confidence-based routing + human override with feedback loop
- **Ops Dashboard** (S4.4): Real-time KPIs, anomaly alerts, override queue, workload balancing
- **SLA Management** (S4.5): Priority tiers, deadline tracking, auto-escalation to managers
- **Multi-Channel Routing** (S4.6): Slack, email, PagerDuty, webhooks with on-call integration + DND
- **Feedback Loop** (S4.7): Continuous signal collection from overrides + sentiment + retraining triggers
- **Context Handoff** (S4.8): Rich escalation summary preserving triage intent + customer history
- **Performance Monitoring** (S4.9): Prometheus metrics, Grafana dashboards, alert rules, runbooks
- **Acceptance Gate** (S4.10): 6 E2E scenarios, 25-record golden set, performance benchmarks

---

## Deliverables Summary

| Item | Title | Focus | Lines |
|------|-------|-------|-------|
| **S4.1** | Anomaly Detection & Risk Signals | EWMA + Isolation Forest, 6 signal types, webhooks | 839 |
| **S4.2** | Proactive Outreach Triggers | Health/engagement/billing/loyalty campaigns, A/B tests | 569 |
| **S4.3** | Escalation & Manual Override | Confidence/safety/sentiment escalation, override UI, feedback | 520 |
| **S4.4** | Operations Dashboard | 4 panels, KPIs, anomaly alerts, override queue, WebSocket | 518 |
| **S4.5** | Escalation Queue & SLA Management | Priority tiers, SLA tracking, auto-escalation, audit trail | 794 |
| **S4.6** | Multi-Channel Escalation | Slack/email/PagerDuty/webhook, on-call, DND, templates | 635 |
| **S4.7** | Feedback Loop & Improvement | Feedback ingestion, override analysis, retraining triggers | 812 |
| **S4.8** | Conversation Continuity & Handoff | Escalation summary, customer context, history, quality score | 647 |
| **S4.9** | Performance Monitoring & Alerting | Prometheus metrics, Grafana dashboards, alert rules, runbooks | 730 |
| **S4.10** | Sprint 4 Acceptance Gate | 6 E2E scenarios, 25-record golden set, benchmarks, CI gate | 841 |

---

## Data Flow Architecture

```
Customer Interaction
       ↓
S2.7: Triage Graph (Intent, Entities, Response)
       ↓
       ├─→ High Confidence? → Resolve (track in S4.9 metrics)
       │
       └─→ Low Confidence / Safety Flag?
              ↓
         S4.3: Escalation Decision
              ↓
         S4.1: Anomaly Detection (in parallel)
         - Churn spike detected?
         - Fraud pattern?
         - Complaint surge?
              ↓
         S4.5: Queue Assignment (Priority, SLA)
              ↓
         S4.6: Multi-Channel Notification
         (Slack + email, respecting DND)
              ↓
         S4.8: Context Handoff Preparation
         (Summary + customer context + history)
              ↓
         Human Agent (Ops Dashboard S4.4)
              ↓
         S4.3: Manual Override (with reason)
              ↓
    Resolution / Callback Decision
              ↓
         S4.7: Feedback Collection
         (Override reason, sentiment shift, outcome)
              ↓
    S3.8 Learning Loop (retraining signal)
    S3.5 Knowledge Gap Analysis (feedback)
              ↓
    S4.9: Metrics & Monitoring
    (Escalation rate, resolution time, cost)
```

---

## Key Decisions

### 1. Anomaly Detection Strategy (S4.1)
- **Algorithm:** EWMA (exponential weighted moving average) for trend/drift + Isolation Forest for point anomalies
- **Rationale:** EWMA is lightweight, real-time-friendly; Isolation Forest handles sudden spikes; ensemble reduces false positives
- **Signals:** 6 types (churn spike, fraud pattern, complaint surge, response delay, volume spike, API error rate)
- **Alternative Rejected:** Deep learning (LSTM) — too slow for real-time; rules-based only — too rigid

### 2. Escalation Trigger Design (S4.3)
- **Primary:** Confidence <50% (from S2.1 classification)
- **Secondary:** Safety flags (fraud, abuse, chargeback), entity extraction failure, KB miss
- **Rationale:** Confidence threshold is fast; safety flags are categorical; entity failure indicates incomplete understanding
- **Alternative Rejected:** Only high-confidence escalate — misses important safety cases

### 3. SLA Management (S4.5)
- **Tiers:** P0 (15 min), P1 (1 hour), P2 (4 hours), P3 (24 hours)
- **Auto-escalation:** Manager notification at breach+5min if unacknowledged
- **Rationale:** Clear tier mapping reduces ambiguity; manager escalation prevents missed SLAs
- **Alternative Rejected:** Soft SLAs (warnings only) — not enough pressure; hard SLAs (reject after deadline) — not customer-friendly

### 4. Multi-Channel Routing (S4.6)
- **Primary:** Slack (fastest in-team communication)
- **Fallback:** Email (most reliable, async-friendly)
- **Escalation:** PagerDuty (management visibility)
- **DND:** Respect team member availability windows
- **Rationale:** Slack for urgency; email for reliability; on-call rotation ensures 24/7 coverage; DND prevents burnout
- **Alternative Rejected:** SMS-only — expensive, limited content; all channels simultaneously — noise/alarm fatigue

### 5. Context Handoff Quality (S4.8)
- **Components:** Escalation summary (2–3 sentences), customer context (health score, trends), history (last 3 attempts), quality score
- **Quality Metric:** Completeness scorer (counts present fields, weights critical ones)
- **Target:** >90% completeness on all handoffs
- **Rationale:** Human agents need context to resolve quickly; quality score prevents degradation over time
- **Alternative Rejected:** Minimal context (just ticket) — human re-triages; full context (verbose) — information overload

### 6. Feedback Loop Closure (S4.7)
- **Sources:** Override reasons (manual), sentiment shift (customer satisfaction), retraining triggers (model accuracy)
- **Collection:** Synchronous (form post-escalation), asynchronous (nightly batch on historical data)
- **Routing:** Override analysis → improve escalation rules (S4.3); sentiment shift → track customer health (S3.6); retraining signals → retrain classifier (S3.8)
- **Rationale:** Multiple feedback channels capture different improvement vectors; async batch doesn't block realtime
- **Alternative Rejected:** Single feedback channel — miss signals; no feedback loop — no continuous improvement

---

## Technical Architecture

### Services

```
┌─────────────────────────────────────────────────────────────┐
│ S4.1 — Anomaly Detector                                    │
│ Real-time EWMA + Isolation Forest ensemble                 │
│ Inputs: Metrics stream (from S3.9, S4.4, S4.5)            │
│ Outputs: AnomalySignal webhook to S4.5 queue              │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.5 — Escalation Queue Manager                            │
│ Priority assignment, SLA tracking, auto-escalation         │
│ Reads: AnomalySignal, Escalation decisions from S4.3      │
│ Outputs: Queued tickets with priority + deadline           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.6 — Multi-Channel Router                                │
│ Dispatcher → Slack | Email | PagerDuty | Webhook          │
│ Respects DND, on-call rotation, retry logic               │
│ Outputs: Notification sent to support team                 │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.4 — Ops Dashboard                                       │
│ WebSocket → Real-time KPIs, override queue, alerts        │
│ Dashboards: agent performance, anomalies, workload         │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
              Human Agent Reviews
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.3 — Override / Accept Decision                          │
│ Human selects: accept agent suggestion OR override         │
│ If override: reason captured (e.g., "customer_confirmed") │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.8 — Context Handoff (already prepared)                  │
│ Enriched with: escalation reason, customer context,        │
│ previous attempts, quality score                           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
              Customer Resolution
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.7 — Feedback Collection                                 │
│ Async: override reason, sentiment, retraining signal      │
│ Routes to: S4.3 (escalation rules), S3.6 (health),        │
│           S3.8 (learning loop)                            │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ S4.9 — Performance Monitoring                              │
│ Prometheus: escalation_rate, resolution_time, cost        │
│ Grafana: 4 dashboards, anomaly detection, alert rules     │
└─────────────────────────────────────────────────────────────┘
```

### Data Models

**Core Tables (PostgreSQL):**
- `escalation_signals` (S4.1): AnomalySignal records
- `escalation_queue` (S4.5): Tickets, priority, SLA deadline, assignment
- `escalation_audit` (S4.5): Audit trail (assign, escalate, resolve, override)
- `override_reason` (S4.3, S4.7): Manual override reason + feedback
- `feedback_signals` (S4.7): Override reason, sentiment shift, retraining signal
- `context_handoff` (S4.8): Escalation summary + customer context + quality score

**Cache (Redis):**
- `anomaly:ewma:{signal_type}`: EWMA state (value, mean, variance)
- `anomaly:isolation_forest:{signal_type}`: Cached model + recent trees
- `escalation:queue:{tenant_id}`: Current queue state (for fast reads)
- `escalation:sla:{ticket_id}`: SLA deadline + breach alert status
- `escalation:on_call`: On-call rotation (synced from PagerDuty hourly)

---

## Shared Infrastructure

| Component | Purpose | Config | Notes |
|-----------|---------|--------|-------|
| **PostgreSQL** | Escalation queue, audit trail, feedback | Replication, hourly backups | Shared with S0–S3 |
| **Redis** | EWMA state, queue cache, on-call cache | 3x replication, TTL=3600s | Sub-second lookups |
| **Celery** | Scheduled tasks (SLA breach check, KG batch, BI refresh) | Beat scheduler, 2 worker pools | Scales horizontally |
| **Prometheus** | Metrics scraping (anomaly detection, queue size, latency) | 15s scrape interval, 15d retention | Global metrics store |
| **Grafana** | Dashboards (agent perf, anomalies, override queue, outcomes) | 4 pre-built dashboards | Shared with S3.9 |
| **AlertManager** | Alert routing (Slack, email, PagerDuty) | Per-tenant routing rules | Integrates with S4.6 |
| **LightGBM** | Account health scoring (S3.4) | Model artifact in S3 + version mgmt | Used in escalation triage |

---

## Testing Strategy

### Tier A (Unit Tests)
- Anomaly detector: EWMA computation, Isolation Forest scoring
- Escalation rules: confidence threshold, safety flag evaluation
- Queue operations: priority scoring, deadline calculation, assignment
- SLA breach detection: time math, state transitions
- Multi-channel template rendering: Jinja2 + variable substitution
- Override reason classification: keyword extraction
- Handoff quality scorer: field presence logic, weight calculations
- Metrics aggregation: counter increments, gauge updates

### Tier B (Integration Tests)
- Redis fallback: queue cache miss → DB read
- Celery task execution: SLA breach check job, nightly KG batch
- Multi-channel delivery: Slack webhook mock, email SMTP mock, PagerDuty API mock
- Escalation flow: S4.1 signal → S4.5 queue → S4.6 notification
- Feedback ingestion: override form → S4.7 processor → S3.8 signal
- On-call rotation sync: hourly cron from PagerDuty

### Tier C (E2E Acceptance)
- Scenario A: Churn escalation (S4.1 signal → S4.2 campaign → S4.5 queue → S4.6 alert)
- Scenario B: Fraud override (S4.3 override → S4.7 feedback → S3.8 retraining trigger)
- Scenario C: Low confidence escalation (S2.7 confidence threshold → S4.3 escalation decision)
- Scenario D: SLA breach auto-escalation (manager notification)
- Scenario E: Multi-channel DND (Slack blocked → email fallback)
- Scenario F: Proactive campaign + tracking (A/B assignment, metrics collection)

### Tier D (A/B Testing)
- Anomaly threshold tuning: sensitivity vs. false positives
- Escalation reason priority: which signals drive decisions?
- Proactive campaign effectiveness: email vs. in-app, personalization impact
- Context handoff quality: does fuller context reduce re-triage rate?
- Multi-channel preference: Slack vs. email adoption by team

### Tier E (Golden Set)
- 25 records covering all 6 acceptance scenarios
- Each record includes: input (signal, triage context), expected output (escalation decision, channels, SLA tier)
- Regression detection: run golden set on every PR

---

## Deployment Checklist

**Infrastructure:**
- [ ] Redis cluster (3 nodes, 6GB RAM, TTL policy configured)
- [ ] PostgreSQL replication setup for escalation tables
- [ ] Celery workers (2 pools: urgent, batch) scaled to expected load
- [ ] Prometheus configured with 15s scrape interval
- [ ] Grafana datasource connected to Prometheus + PostgreSQL
- [ ] AlertManager deployed + routed to Slack/email/PagerDuty

**Configuration:**
- [ ] Anomaly detector thresholds tuned (EWMA α, Isolation Forest threshold)
- [ ] SLA tiers configured per tenant (P0–P3 deadlines)
- [ ] Multi-channel credentials (Slack token, email SMTP, PagerDuty API key, webhook URLs)
- [ ] On-call rotation synced with PagerDuty
- [ ] DND schedules imported for support team
- [ ] Override reason taxonomy defined
- [ ] Escalation routing rules (confidence threshold, safety flags, entity failures)

**Code & Data:**
- [ ] S4.1–S4.9 services deployed and health-checked
- [ ] Database migrations applied (escalation_queue, audit, feedback tables)
- [ ] Alembic version pinned
- [ ] 25-record golden set loaded into test harness
- [ ] Grafana dashboards imported (4 panels pre-built)
- [ ] AlertManager rules deployed + tested

**Quality:**
- [ ] Acceptance tests pass (6 scenarios + golden set, all benchmarks met)
- [ ] Performance baseline: anomaly <2s, escalation <5s, routing <3s, handoff >90% quality
- [ ] Monitoring active: escalation rate, SLA breach rate, context quality, channel delivery
- [ ] Runbooks written: common escalation scenarios, troubleshooting
- [ ] Team trained: ops dashboard, override queue, feedback loop
- [ ] CI gate enabled: new PRs must pass acceptance tests

---

## Performance Targets

| Metric | Target | SLA | Measurement |
|--------|--------|-----|-------------|
| Anomaly detection (p99) | <2s | Critical | Webhook delivery latency |
| Escalation latency (p99) | <5s | Critical | Triage decision → queue assignment |
| Multi-channel routing (p99) | <3s | Critical | Escalation trigger → all notifications sent |
| Ops dashboard WebSocket (p95) | <500ms | SLA | Message latency from backend to browser |
| Context handoff completeness (avg) | >90% | SLA | Quality scorer on all handoffs |
| SLA accuracy (detection) | >95% | SLA | Precision of breach detection |
| Feedback ingestion latency (p99) | <1s | SLA | Override submission → processing |
| Queue assignment latency (p99) | <1s | SLA | Priority calculation + assignment |

---

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Anomaly false positives** | Alert fatigue, ops burnout | EWMA + Isolation Forest ensemble; threshold tuning; supervised threshold per signal type |
| **Escalation cascade** | Recursive escalations (escalate→escalate) | Max escalation depth = 2; confidence guard on first escalation |
| **SLA deadline misses** | Customer SLA breach, reputation | Auto-escalation to manager; proactive monitoring; queue prioritization |
| **Multi-channel delivery failure** | Escalations not reaching team | Fallback routing; retry with exponential backoff; audit trail logging |
| **Context handoff incomplete** | Human re-triages (wasted effort) | Completeness scorer; validation tests; regular quality audits |
| **Override reason misclassification** | Feedback loop trains on bad labels | Manual review of top override reasons; feedback loop confidence thresholding |
| **PagerDuty/Slack/email outage** | Escalations lost | Fallback webhooks + local queue; retry storage in PostgreSQL |
| **Team member burnout** | On-call overload, high escalation rate | DND scheduling; workload balancing algorithm; escalation rate monitoring + alerts |

---

## Sprint 5 Handoff

**Proactive Intelligence & Optimization** (S5.1–S5.10):
- S5.1: Customer lifecycle stage detection (new, growth, mature, churn risk)
- S5.2: Predictive insights (next issue prediction, seasonal patterns)
- S5.3: Recommendation engine (suggest knowledge articles, self-service paths)
- S5.4: Campaign optimization (dynamic offer generation, personalization)
- S5.5: Cost analysis & ROI (cost per escalation, automation ROI per segment)
- S5.6: Knowledge base optimization (update recommendations from gaps + feedback)
- S5.7: Team efficiency (agent productivity, tool adoption, skill gaps)
- S5.8: Customer outcome tracking (NPS trend, churn prevention success rate, LTV impact)
- S5.9: Market intelligence (competitive feature requests, emerging issues)
- S5.10: Sprint 5 acceptance gate + production readiness

---

## Summary

Sprint 4 completes the reactive-to-proactive transformation. With real-time anomaly detection, intelligent escalation routing, multi-channel notifications, and continuous feedback loops, the platform is now **always listening** and **always learning**. Operations teams gain visibility and control via the dashboard. Customers experience proactive support before issues escalate. The learning loop ensures the system improves over time.

**Key Outcomes:**
- Real-time anomaly detection (<2s latency)
- Confidence-driven escalation with human override
- Multi-channel routing with on-call integration
- SLA management with auto-escalation
- Rich context handoff (>90% completeness)
- Continuous feedback loop powering S3.8 & S3.5
- Comprehensive ops dashboards + alerts
- 25-record golden set + CI gate for regression prevention

**Total Project Progress:** Sprints 0–4 complete (50 deliverables, ~25,900 lines). Ready for implementation or Sprint 5 (Intelligence & Optimization).
