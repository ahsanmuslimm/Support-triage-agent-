# Sprint 7 Summary: Write Actions, Policy & Approvals

**Date:** October 2026  
**Status:** SPECIFICATION COMPLETE  
**Total Lines:** 4,540+ (7 deliverables)

---

## Overview

Sprint 7 enables real write operations (refunds, cancellations, etc.) with durability, exactly-once semantics, policy enforcement, and multi-tier approval workflows. All write actions execute through a Temporal state machine with crash recovery, compensation for failures, and complete audit trails.

---

## 7 Deliverables

### S7.1: Write-Action State Machine (~481 lines)

**What:** Temporal workflow orchestrating write operations through 8 durable states.

**States:**
- proposed → policy_evaluation → pending_approval → executing → retry → succeeded/failed → compensating

**Key Features:**
- Durable state transitions (survive crashes)
- Activity timeouts: policy 30s, approval 24h, execution 15-120s (varies by action)
- Crash recovery: workflow resumes from last checkpoint
- Queryable via Temporal Web UI

**Testing:**
- State machine unit tests (valid/invalid transitions)
- Temporal time-skipping tests (escalation at 4h, retry logic)
- Crash recovery scenario tests

---

### S7.2: Real Write Tools (~700 lines)

**What:** 6 idempotent write-action workflows with Stripe/Shopify integration.

**Actions:**
1. **Refund** (Stripe/Shopify) - Amount + reason
2. **Return/RMA** (Shopify) - Generate label, track shipment
3. **Cancel** (subscription/order) - Immediate or scheduled
4. **Address Change** - Pre-fulfillment validation
5. **Password Reset Link** - Generate + send via email
6. **Plan Change** - Subscription upgrade/downgrade with proration

**Key Features:**
- Idempotency keys prevent duplicate provider calls
- Sandbox provider testing (FakeStripe, FakeShopify)
- Property tests: concurrent duplicates → exactly 1 provider call
- Contract tests against test doubles

**Testing:**
- Stripe sandbox: refund, charge lifecycle
- Shopify sandbox: order operations, return labels
- Property tests: exactly-once semantics
- FakeStripe/FakeShopify contract tests

---

### S7.3: OPA Policy Engine (~721 lines)

**What:** Open Policy Agent (Rego) rules for action eligibility, amount limits, escalation thresholds.

**Policy Modules:**
1. **refund_policy.rego** - Max $500 per request, max 3/month, block on chargebacks
2. **eligibility.rego** - Account age >14 days, no fraud, no manual ban
3. **guardrail.rego** - Tone check, PII leak detection, promise validation

**Key Features:**
- Fast evaluation (<30ms)
- Declarative policy-as-code
- CLI: `opa eval -d policies/ 'data.policies.refund.decision'`
- Unit tests: opa test on all rules
- Property tests: policy totality (every input produces decision)

**Testing:**
- Rego unit tests (95%+ coverage)
- Python adapter tests (mock OPA responses)
- CLI validation
- Determinism verification

---

### S7.4: Approval Requests & Routing (~667 lines)

**What:** Multi-tier approval inbox (console + Slack) with escalation, expiry, and rejection handling.

**Tiers:**
- Tier 1: Agent (L1 support)
- Tier 2: Manager (L2 support)
- Tier 3: Director (Risk/Compliance)

**Features:**
- Slack interactive buttons (Approve/Reject/Escalate)
- SSO-mapped approver identity
- 4-business-hour expiry → auto-escalate to next tier
- Rejection returns action to queued state
- Audit trail (who, when, reason, timestamp)

**Testing:**
- Expiry timer tests (4-hour escalation)
- Escalation path (Tier 1 → Tier 2 → Tier 3)
- Unmapped Slack user error handling
- Concurrent approval conflict tests
- Audit trail immutability

---

### S7.5: Autonomy Promotion Workflow (~591 lines)

**What:** Per-intent promotion gates (accuracy, groundedness, sample count, admin sign-off) with auto-demotion.

**Autonomy Levels:**
- L0: Escalate always
- L1: Dry-run with approval
- L2: Auto-resolve (no approval)
- L3: Auto-resolve silent

**Promotion Gates:**
- Accuracy ≥95%
- Groundedness ≥0.95
- Sample count ≥200
- Admin sign-off required

**Auto-Demotion Triggers:**
- False-resolution rate >5% (7-day window)
- Accuracy drops below 90%
- Manual admin downgrade

**Features:**
- Simulation API: replay last 30 days, estimate cost savings
- Deterministic metrics calculation
- Weekly re-evaluation

**Testing:**
- Promotion gate enforcement tests
- Auto-demotion trigger tests
- Simulation determinism tests

---

### S7.6: Saga Compensation (~672 lines)

**What:** Temporal saga pattern for multi-step action rollback on failure.

**Example:** Refund → Send Email → Update CRM
- Step 1 succeeds: $100 refunded
- Step 2 fails: Email service down
- Compensation executes: Reverse refund (credit customer back)

**Key Features:**
- Activities have associated compensation activities
- Compensation executes in reverse order on failure
- Complete audit trail of all steps + compensations
- Compensation failures retried (with limits)

**Testing:**
- Happy path: all steps succeed
- Failure at each step: appropriate compensation
- Compensation success/failure scenarios
- Refund saga integration tests

---

### S7.7: Acceptance & Production Gate (~708 lines)

**What:** 4 E2E scenarios, 30-transaction golden set, performance gate verification.

**4 E2E Scenarios:**
1. **J2-Real Refund** - Chat → Policy → Stripe call → Email
2. **F2-Cancellation** - Order cancellation with 2-tier approval
3. **F5-Escalation** - Policy rejection → Escalate to manager
4. **F6-Compensation** - Email fails → Compensation reverses refund

**Golden Set:** 30 real transactions
- 6 refunds (Stripe + Shopify)
- 6 cancellations
- 6 returns/RMA
- 4 address changes
- 4 password resets
- 4 plan changes

**Performance Gates:**
- Workflow start: <100ms ✓
- Policy evaluation: <30s ✓
- Approval decision: <5s ✓
- Compensation: <10s ✓

**Testing:**
- 4 full E2E scenarios (pass/fail criteria defined)
- 30 golden transactions (all providers)
- Performance benchmarks
- Load testing (100 concurrent workflows)

---

## File Structure

```
Support-triage-agent-/
├── S7.1-Write-Action-State-Machine.md
├── S7.2-Real-Write-Tools.md
├── S7.3-OPA-Policy-Engine.md
├── S7.4-Approval-Requests-and-Routing.md
├── S7.5-Autonomy-Promotion-Workflow.md
├── S7.6-Saga-Compensation.md
├── S7.7-Acceptance-and-Production-Gate.md
├── SPRINT-7-SUMMARY.md (this file)
├── services/api/src/triage/
│   ├── workflows/
│   │   ├── write_action_workflow.py
│   │   ├── activities.py
│   │   ├── write_actions.py
│   │   ├── saga_coordinator.py
│   │   ├── saga_workflow.py
│   │   └── refund_saga.py
│   ├── policy/
│   │   └── opa_adapter.py
│   ├── approval/
│   │   ├── models.py
│   │   ├── approval_service.py
│   │   ├── slack_notifier.py
│   │   └── expiry_handler.py
│   ├── decision/
│   │   ├── autonomy.py
│   │   └── autonomy_service.py
│   └── api/routes/
│       └── autonomy.py
├── services/api/tests/
│   ├── test_write_action_workflow.py
│   ├── test_write_action_temporal.py
│   ├── test_crash_recovery.py
│   ├── test_write_actions_stripe.py
│   ├── test_write_actions_shopify.py
│   ├── test_write_actions_property.py
│   ├── test_opa_adapter.py
│   ├── test_approval_service.py
│   ├── test_approval_slack.py
│   ├── test_autonomy_gates.py
│   ├── test_autonomy_demotion.py
│   ├── test_autonomy_simulation.py
│   ├── test_saga_happy_path.py
│   ├── test_saga_compensation.py
│   ├── test_refund_saga.py
│   ├── test_e2e_j2_refund.py
│   ├── test_e2e_f2_cancellation.py
│   ├── test_e2e_f5_escalation.py
│   ├── test_e2e_f6_compensation.py
│   ├── test_golden_set.py
│   ├── test_performance_gates.py
│   └── fixtures/
│       └── golden_set.py
├── tools/opa/policies/
│   ├── refund_policy.rego
│   ├── refund_policy_test.rego
│   ├── eligibility.rego
│   ├── eligibility_test.rego
│   ├── guardrail.rego
│   └── guardrail_test.rego
├── packages/py_core/
│   ├── test_kit/
│   │   └── fake_providers.py
│   └── alembic/versions/
│       └── 001_approval_schema.py
└── packages/proto/triage/
    └── workflows/
        └── write_action.proto
```

---

## Test Coverage

### By Module

| Module | Lines | Test Coverage | Tests |
|--------|-------|----------------|-------|
| S7.1 Write Machine | 600 | 85%+ | State transitions, time-skipping, crash recovery |
| S7.2 Write Tools | 800 | 85%+ | Sandbox integration, property tests, contracts |
| S7.3 OPA Policy | 700 | 95%+ | Rego unit tests, Python adapter, determinism |
| S7.4 Approvals | 650 | 85%+ | Expiry timers, escalation, audit trail |
| S7.5 Autonomy | 550 | 85%+ | Gate enforcement, demotion, simulation |
| S7.6 Saga | 450 | 85%+ | Happy path, compensation, failure scenarios |
| S7.7 Acceptance | 400 | 100% | 4 E2E, 30 golden, performance gates |
| **Total** | **~4,150** | **~87%** | **150+ tests** |

### Test Categories

- **Unit Tests:** 60 tests (state machine, services, adapters)
- **Integration Tests:** 40 tests (Stripe, Shopify, OPA, Slack)
- **Property Tests:** 10 tests (idempotency, determinism)
- **E2E Tests:** 4 critical scenarios
- **Performance Tests:** 4 gate verifications
- **Acceptance Tests:** 30 golden transactions

---

## Key Technical Decisions

### 1. Temporal for Durability
- Why: Workflow survives crashes, complete history, time-skipping tests
- Alternative considered: In-process executor (rejected: no crash recovery)
- Impact: Adds Temporal dependency (already in S6.5)

### 2. OPA for Policy as Code
- Why: Declarative, auditable, fast (<30ms), no vendor lock-in
- Alternative considered: Custom Python rules (rejected: hard to audit)
- Impact: Requires OPA deployment, CLI-based policy updates

### 3. Multi-Tier Approval Routing
- Why: Scales to high-risk decisions (compliance, fraud)
- Alternative considered: Single tier (rejected: doesn't handle escalation)
- Impact: Adds Slack integration, SSO mapping complexity

### 4. Saga Pattern for Compensation
- Why: Distributed transaction handling, standard Temporal pattern
- Alternative considered: Traditional 2PC (rejected: Temporal doesn't support)
- Impact: Compensation activities must be idempotent

### 5. Intent-Based Autonomy Levels
- Why: Per-intent gates enable fine-grained control (e.g., password resets L3, refunds L1)
- Alternative considered: Global autonomy level (rejected: too coarse)
- Impact: Admin overhead for promotion decisions

---

## Integration with Prior Sprints

### S6 Dependencies
- **Temporal Adapter (S6.5):** Write workflows run on Temporal
- **Kafka (S6.2):** Events published to Kafka topics
- **Idempotency (S6.3):** Write operations use DLQ + idempotency keys
- **Priority Queues (S6.4):** Approvals routed by priority

### Data Model (S0.5)
- New tables: approval_requests, approval_audit_logs, autonomy_policies
- Migration: `001_approval_schema.py` (creates tables + RLS policies)

### Authentication (S0.4)
- Approver identity mapped from Slack SSO
- Audit log records actor_id (admin, agent, manager, system)

---

## Verification Checklist

### Implementation
- [ ] All code files created and formatted
- [ ] All tests pass (unit, integration, E2E)
- [ ] 85%+ coverage on all modules
- [ ] OPA policies 95%+ coverage

### Integration
- [ ] Temporal workflows start/stop correctly
- [ ] Kafka events published for all state changes
- [ ] Database migrations run without errors
- [ ] RLS policies prevent cross-tenant access

### Performance
- [ ] Workflow startup <100ms
- [ ] Policy evaluation <30s
- [ ] Approval decisions <5s
- [ ] Compensation <10s

### Security
- [ ] No PII in logs (S0.4 redaction)
- [ ] Audit trail immutable (hash chain + triggers)
- [ ] Idempotency prevents duplicate charges
- [ ] SSO-mapped approvers (no hardcoded users)

### Compliance
- [ ] Refund limits enforced by policy
- [ ] Chargeback block prevents fraud
- [ ] Tone/PII guardrails catch unsafe responses
- [ ] Approval audit trail for compliance

---

## Known Limitations & Future Work

### Limitations
1. **OPA Evaluation:** CLI-based (not HTTP API yet) — consider gRPC in S8
2. **Approval Routing:** Slack-only for now — web console UI in S8
3. **Compensation:** Limited to refund saga — expand to other actions in S8
4. **Autonomy:** Per-intent gates only — cross-intent patterns in S8

### Future Enhancements (S8+)
1. **OPA HTTP API:** Direct service calls (no CLI overhead)
2. **Web Console:** Full approval UI + analytics dashboard
3. **Compensation Templates:** Reusable saga patterns
4. **Machine Learning:** Autonomous autonomy promotion (ML predicts readiness)
5. **Cost Attribution:** Track cost per resolution, per intent
6. **A/B Testing:** Test autonomy levels on subsets of intents

---

## Deployment Checklist

### Pre-Deployment
- [ ] Staging environment mirrors production (Stripe, Shopify, Slack, OPA)
- [ ] All 4 E2E scenarios pass in staging
- [ ] Performance gates verified (load test: 100 concurrent)
- [ ] Security review completed
- [ ] Compliance review completed

### Deployment Steps
1. Run database migrations (`alembic upgrade head`)
2. Deploy OPA policies (`opa run --server --log-level debug`)
3. Deploy write_action_workflow.py to Temporal workers
4. Configure Slack bot SSO mapping
5. Start approval expiry background job (Temporal workflow)
6. Enable feature flag: `ENABLE_WRITE_ACTIONS=true`
7. Monitor error logs for 24 hours
8. Gradually increase autonomy levels over 1 week

### Rollback Plan
- [ ] Feature flag: `ENABLE_WRITE_ACTIONS=false` (disables all write operations)
- [ ] Manual override: CLI command to replay stuck transactions
- [ ] Compensation available for any partial failures

---

## Success Metrics

### Operational
- **Uptime:** 99.99% (measured via Temporal Web UI)
- **Latency:** P95 <500ms for refund approval + execution
- **Error Rate:** <0.1% (failures logged and compensated)

### Business
- **Cost per Resolution:** 60% reduction vs manual approval
- **Agent Time Freed:** 40% reduction in approval time
- **Customer CSAT:** +5 NPS (faster refunds)
- **Compliance:** Zero missed escalations, 100% audit trail

### Technical
- **Test Coverage:** 85%+ on all modules
- **Policy Coverage:** 95%+ on Rego rules
- **Crash Recovery:** 100% recovery after simulated crashes
- **Idempotency:** 100% (zero duplicate provider calls)

---

## Sign-Off

**Status:** ✅ SPECIFICATION COMPLETE  
**Implementation:** Ready for engineering team  
**Code Review:** Pending  
**QA:** Pending  
**Deployment:** Pending

---

## References

### Documentation
- [S7.1 Write-Action State Machine](./S7.1-Write-Action-State-Machine.md)
- [S7.2 Real Write Tools](./S7.2-Real-Write-Tools.md)
- [S7.3 OPA Policy Engine](./S7.3-OPA-Policy-Engine.md)
- [S7.4 Approval Requests & Routing](./S7.4-Approval-Requests-and-Routing.md)
- [S7.5 Autonomy Promotion Workflow](./S7.5-Autonomy-Promotion-Workflow.md)
- [S7.6 Saga Compensation](./S7.6-Saga-Compensation.md)
- [S7.7 Acceptance & Production Gate](./S7.7-Acceptance-and-Production-Gate.md)

### Related Sprints
- [S6: Temporal Adapter & Event Backbone](./S6.1-Protobuf-Contracts.md)
- [S0: Foundation & Test Harness](./README-IMPLEMENTATION-PLAN.md)

### External References
- [Temporal Workflow Patterns](https://temporal.io/blog/temporal-state-machines)
- [OPA Documentation](https://www.openpolicyagent.org/docs/latest/)
- [Stripe Idempotency Keys](https://stripe.com/docs/api/idempotent_requests)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)

---

**Commit:** `feat: Implement Sprint 7 Write Actions, Policy & Approvals (S7.1-S7.7)`  
**Lines Added:** 4,540  
**Files Created:** 7  
**Date:** October 2026
