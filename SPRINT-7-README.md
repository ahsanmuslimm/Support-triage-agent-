# Sprint 7 Implementation Guide

**Sprint 7: Write Actions, Policy & Approvals**  
**Status:** Specification Complete | Ready for Implementation  
**Total Scope:** ~4,750 lines of code (7 deliverables)

---

## Quick Start

### Read First
1. **[SPRINT-7-SUMMARY.md](./SPRINT-7-SUMMARY.md)** — 2-page overview
2. **[S7.1-Write-Action-State-Machine.md](./S7.1-Write-Action-State-Machine.md)** — Core orchestration
3. **[S7.2-Real-Write-Tools.md](./S7.2-Real-Write-Tools.md)** — Provider integrations
4. **[S7.3-OPA-Policy-Engine.md](./S7.3-OPA-Policy-Engine.md)** — Policy enforcement
5. **[S7.4-Approval-Requests-and-Routing.md](./S7.4-Approval-Requests-and-Routing.md)** — Approval workflows
6. **[S7.5-Autonomy-Promotion-Workflow.md](./S7.5-Autonomy-Promotion-Workflow.md)** — Autonomy gates
7. **[S7.6-Saga-Compensation.md](./S7.6-Saga-Compensation.md)** — Failure compensation
8. **[S7.7-Acceptance-and-Production-Gate.md](./S7.7-Acceptance-and-Production-Gate.md)** — E2E verification

---

## What Sprint 7 Delivers

### Real Write Operations
- Refund charges (Stripe/Shopify)
- Cancel orders/subscriptions
- Generate return labels
- Update customer data (address, plan)
- Send password reset links

### Policy & Compliance
- Open Policy Agent (OPA) rules for eligibility
- Amount limits, frequency caps, fraud blocks
- Tone/PII guardrails
- Audit trail for compliance

### Multi-Tier Approvals
- Slack integration with interactive buttons
- Agent → Manager → Director escalation
- 4-hour expiry with auto-escalation
- SSO-mapped approver identity

### Crash Recovery & Durability
- Temporal workflow state machine
- Crash recovery from last checkpoint
- Complete audit trail
- Exactly-once semantics (idempotency keys)

### Compensation & Rollback
- Multi-step action support (saga pattern)
- Automatic compensation on failure
- Reverse Stripe refunds, undo CRM records
- Complete failure recovery

### Per-Intent Autonomy
- Accuracy gates (≥95%)
- Groundedness gates (≥0.95)
- Auto-demotion on quality degradation
- Simulation: replay & estimate savings

---

## Implementation Order

### Phase 1: Foundation (Week 1)
1. **S7.1** - Write-Action State Machine
   - Define workflow states and transitions
   - Create Temporal workflow
   - Unit tests + time-skipping tests

2. **S7.3** - OPA Policy Engine
   - Write Rego policies (refund, eligibility, guardrails)
   - Python adapter + CLI integration
   - Unit tests + CLI validation

### Phase 2: Operations (Week 2)
3. **S7.2** - Real Write Tools
   - Implement 6 write actions (refund, cancel, return, etc.)
   - Stripe/Shopify sandbox integration
   - Idempotency key tracking
   - Property tests (exactly-once)

4. **S7.4** - Approval Requests & Routing
   - Approval request models + service
   - Slack bot integration + SSO mapping
   - Expiry timer + escalation logic
   - Audit trail

### Phase 3: Advanced (Week 3)
5. **S7.5** - Autonomy Promotion Workflow
   - Promotion gate evaluation
   - Auto-demotion triggers
   - Simulation endpoint (replay 30 days)
   - Tests for gates + demotion

6. **S7.6** - Saga Compensation
   - Saga coordinator + workflow
   - Compensation activity definitions
   - Example: refund → email → CRM saga
   - Failure + compensation tests

### Phase 4: Verification (Week 4)
7. **S7.7** - Acceptance & Production Gate
   - 4 E2E scenarios (J2, F2, F5, F6)
   - 30 golden transactions
   - Performance gate tests
   - Load testing (100 concurrent)

---

## File Structure

### Source Code
```
services/api/src/triage/
├── workflows/
│   ├── write_action_workflow.py    # S7.1 - State machine
│   ├── activities.py                # S7.1 - Activity definitions
│   ├── write_actions.py             # S7.2 - 6 actions
│   ├── saga_coordinator.py          # S7.6 - Saga model
│   ├── saga_workflow.py             # S7.6 - Saga orchestration
│   └── refund_saga.py               # S7.6 - Example saga
├── policy/
│   └── opa_adapter.py               # S7.3 - OPA interface
├── approval/
│   ├── models.py                    # S7.4 - Approval models
│   ├── approval_service.py          # S7.4 - Business logic
│   ├── slack_notifier.py            # S7.4 - Slack integration
│   └── expiry_handler.py            # S7.4 - Expiry + escalation
└── decision/
    ├── autonomy.py                  # S7.5 - Autonomy models
    ├── autonomy_service.py          # S7.5 - Promotion logic
    └── api/routes/autonomy.py       # S7.5 - Simulation endpoint
```

### Policy Rules
```
tools/opa/policies/
├── refund_policy.rego              # S7.3 - Refund rules
├── refund_policy_test.rego         # S7.3 - Refund tests
├── eligibility.rego                 # S7.3 - Eligibility rules
├── eligibility_test.rego            # S7.3 - Eligibility tests
├── guardrail.rego                   # S7.3 - Guardrail rules
└── guardrail_test.rego              # S7.3 - Guardrail tests
```

### Tests
```
services/api/tests/
├── test_write_action_workflow.py    # S7.1 - State machine tests
├── test_write_action_temporal.py    # S7.1 - Time-skipping tests
├── test_crash_recovery.py           # S7.1 - Recovery tests
├── test_write_actions_*.py          # S7.2 - Write action tests
├── test_opa_adapter.py              # S7.3 - OPA tests
├── test_approval_*.py               # S7.4 - Approval tests
├── test_autonomy_*.py               # S7.5 - Autonomy tests
├── test_saga_*.py                   # S7.6 - Saga tests
├── test_e2e_*.py                    # S7.7 - E2E scenarios
└── test_performance_gates.py        # S7.7 - Performance gates
```

### Database
```
packages/py_core/alembic/versions/
└── 001_approval_schema.py           # S7.4 - Approval tables + RLS
```

---

## Development Workflow

### 1. Setup
```bash
# Start dependencies
docker-compose up -d temporal postgres opa redis

# Create venv
uv sync

# Run migrations
alembic upgrade head
```

### 2. Implement Each Deliverable
```bash
# Example: S7.1
cd services/api
python -m pytest tests/test_write_action_workflow.py -v

# Run with coverage
pytest --cov=src/triage/workflows --cov-report=html
```

### 3. Run All Tests
```bash
# All S7 tests
pytest services/api/tests/test_*.py -v --cov=src/triage

# Specific module
pytest services/api/tests/test_approval_service.py -v
```

### 4. Verify E2E
```bash
# E2E scenarios
pytest -m e2e services/api/tests/test_e2e_*.py -v

# Golden set
pytest services/api/tests/test_golden_set.py -v

# Performance gates
pytest -m performance services/api/tests/test_performance_gates.py -v
```

---

## Key Dependencies

### Temporal
- Framework: `temporalio` 1.24+
- Server: Docker (from S6.5)
- Features: Workflows, activities, time-skipping tests

### OPA
- Framework: `opa` CLI, Python SDK
- Server: Docker or HTTP API
- Features: Rego policies, deterministic evaluation

### Providers
- **Stripe:** `stripe` Python SDK (sandbox)
- **Shopify:** `shopify-python-api` (GraphQL client)
- **Email:** Mock service (no external service)

### Testing
- **Fakes:** FakeStripe, FakeShopify (in py_core/test_kit)
- **Slack:** Mock WebClient
- **Database:** PostgreSQL + SQLAlchemy

---

## Testing Strategy

### Coverage Targets
- Unit tests: 85%+ coverage
- Integration tests: Stripe, Shopify, OPA
- E2E tests: 4 critical scenarios
- Performance tests: All gates met
- Overall: 87%+ project coverage

### Test Pyramid
```
         E2E Tests (4 scenarios)
        /                      \
    Integration Tests (40 tests)
    /                          \
Unit Tests (60 tests)
```

### Key Test Scenarios
- **S7.1:** State machine transitions, crash recovery
- **S7.2:** Sandbox provider calls, idempotency
- **S7.3:** Policy evaluation, Rego coverage
- **S7.4:** Approval routing, escalation, Slack
- **S7.5:** Promotion gates, auto-demotion, simulation
- **S7.6:** Saga happy path, compensation, failures
- **S7.7:** 4 E2E scenarios, 30 golden, performance

---

## Performance Checklist

- [ ] Workflow startup: <100ms
- [ ] Policy evaluation: <30s
- [ ] Approval decision: <5s
- [ ] Compensation execution: <10s
- [ ] E2E J2 refund: <5s (total)
- [ ] Load test (100 concurrent): <10s P95

---

## Deployment Checklist

### Pre-Deployment
- [ ] All tests pass (unit, integration, E2E)
- [ ] 87%+ coverage achieved
- [ ] Security review completed
- [ ] Compliance review completed
- [ ] Load testing done (100 concurrent)

### Deployment Steps
1. Run database migrations
2. Deploy OPA policies
3. Deploy write_action_workflow to Temporal
4. Configure Slack bot SSO mapping
5. Start approval expiry background job
6. Enable `ENABLE_WRITE_ACTIONS` feature flag
7. Monitor for 24 hours
8. Gradually increase autonomy levels

### Rollback
- Disable `ENABLE_WRITE_ACTIONS` feature flag
- Use manual CLI to replay stuck transactions

---

## Troubleshooting

### Temporal Workflow Hangs
- Check: Temporal server running (`docker ps`)
- Check: Activity implementation exists
- Solution: Restart worker, replay workflow

### OPA Policy Errors
- Check: OPA server running (`opa run --server`)
- Check: Policies loaded (`opa test tools/opa/policies/`)
- Solution: Fix Rego syntax, reload policies

### Approval Escalation Not Working
- Check: Timezone for 4-hour window
- Check: Approval expiry_at timestamp
- Solution: Run `check_expiring_approvals` activity manually

### Provider Integration Fails
- Check: Sandbox credentials configured (.env)
- Check: Idempotency key unique
- Solution: Use FakeStripe/FakeShopify for testing

---

## References

### External Docs
- [Temporal Documentation](https://docs.temporal.io/)
- [OPA Documentation](https://www.openpolicyagent.org/docs/)
- [Stripe API Reference](https://stripe.com/docs/api)
- [Shopify GraphQL API](https://shopify.dev/api/admin-graphql)

### Internal Docs
- [S6: Temporal Adapter](./S6.5-Temporal-Adapter.md)
- [S0: Foundation](./README-IMPLEMENTATION-PLAN.md)

---

## Questions?

Refer to the detailed specification files (S7.1–S7.7) for implementation details.

---

**Ready to implement? Start with S7.1: Write-Action State Machine.**
