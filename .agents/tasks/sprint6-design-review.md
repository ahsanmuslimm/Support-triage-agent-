# Sprint 6 Technical Design Review

**Reviewer:** Design Review Agent (Fresh Read)  
**Date:** 2026-10-27  
**Status:** REVIEW COMPLETE  

---

## Executive Summary

This review examines the Sprint 6 design on its own merits without relying on prior implementation context. The design is **comprehensive and well-structured** but contains **6 actionable findings (2 HIGH, 4 MEDIUM)** that must be resolved before implementation. The HIGH findings concern critical operational safety (Debezium snapshot replay); the MEDIUM findings address ambiguity in feature flags, activity error handling, and testing completeness.

**Verdict: CHANGES_REQUESTED** (2 HIGH + 4 MEDIUM findings detected)

---

## Verified Assumptions (Passed Source Inspection)

The design makes specific claims about the MVP codebase. All claims verified against actual source:

✓ **MVP Seam Points (Section 1 claims):**
- `triage.ingestion.outbox.OutboxWriter` class exists (services/api/src/triage/ingestion/outbox.py:9)
- `triage.ingestion.outbox.OutboxPoller` class exists (services/api/src/triage/ingestion/outbox.py:96)
- `triage.agent.graph.TriageAgentGraph` class exists (services/api/src/triage/agent/graph.py:29)

✓ **Activity Dependencies (Section 6.2 H3 fix claims):**
All 8 activity implementations verified to have corresponding utility classes:
- `IntentClassifier` exists (triage/classification/classifier.py:27) ✓
- `RuleBasedEntityExtractor` exists (triage/entity/extractor.py:13) ✓
- `DecisionMatrix` exists (triage/decision/matrix.py:17) ✓
- `HybridRetriever` exists (triage/retrieval/hybrid.py:23) ✓
- `ResponseGenerator` exists (triage/generation/generator.py:24) ✓
- `OutputValidator` exists (triage/generation/output_validator.py:23) ✓
- `ToolExecutor` exists (triage/tools/executor.py:26) ✓
- `EscalationRouter` (referenced in activities.py) — **NOT VERIFIED** (see Unverified Assumptions)

---

## Unverified/Wrong Assumptions

**CRITICAL: EscalationRouter class not found**

The design references `triage.escalation.router.EscalationRouter` in activities.py (6.2) but this class could not be located in the codebase. This is needed by the `escalate_activity` but may not exist yet.

**Recommendation:** Verify this exists or is planned for Sprint 5/6. If not, this is a blocking dependency for S6.5.

---

## Findings (by Severity)

### HIGH Findings

#### **H1: Debezium Snapshot Re-Emission Risk — Incomplete Pre-Migration Mitigation**

**Location:** Section 3.2 (Debezium PostgreSQL Connector) + Section 3.2.1

**Problem:**
The design includes a pre-migration checklist (Section 3.2.1) to prevent Debezium from re-emitting old unpublished events on connector restart. However, the checklist is:
- **Procedural only** (written instructions, not automated)
- **Not enforced** by the connector configuration itself
- **Relies on manual execution** of SQL cleanup (Step 3: "mark old events as published")
- **No explicit timeout-based approach** — the grace period ("clean up events >1 hour old") is human-configured without automation

If a human skips Step 3 or miscalculates the grace period, the connector will re-emit old events to Kafka, causing duplicate processing and potential data consistency issues.

**Concrete Fix:**
Provide an automated pre-migration check script that:
1. Queries `SELECT COUNT(*) as unpublished_count FROM outbox_events WHERE published_at IS NULL AND created_at > NOW() - INTERVAL '1 hour'`
2. If count > 0, **fail the deployment** with a clear error message
3. Provide a remediation command that marks old events as published automatically
4. Embed this check in a CI/CD pre-flight task (e.g., a pre-deployment health check)

Alternatively, configure the Debezium connector to run this check and fail on misconfiguration:
```json
{
  "snapshot.mode": "initial",
  "snapshot.delimiter.start": "**",
  "snapshot.delimiter.end": "**",
  "snapshot.delay.ms": 0,
  "snapshot.query": "SELECT * FROM triage.outbox_events WHERE published_at IS NOT NULL",
  "include_only_published_events": true  // Hypothetical: filter out unpublished events during snapshot
}
```

**Severity:** HIGH (data consistency; silent duplicate processing if missed)

---

#### **H2: Debezium Connector Configuration Incomplete — Field Mapping Unvalidated**

**Location:** Section 3.2 (Debezium PostgreSQL Connector — connector-config.json)

**Problem:**
The design states:
> "Field mappings validated against actual `outbox_events` schema: `id`, `tenant_id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `created_at`, `published_at` (from `services/api/src/triage/models/events.py`)"

However:
- No actual schema definition is provided
- The connector config does NOT list field mappings explicitly
- The transform `transforms.outbox.table.field.event.key: tenant_id` assumes this column exists but doesn't verify it
- The filter transform assumes a column `published_at` with NULL values, but if the schema differs, the connector will fail silently

**Concrete Fix:**
1. Explicitly document the `outbox_events` table schema (add to design or as a separate SQL DDL):
```sql
CREATE TABLE triage.outbox_events (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  aggregate_type VARCHAR(100) NOT NULL,
  aggregate_id VARCHAR(255) NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  published_at TIMESTAMP WITH TIME ZONE NULL,
  FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
```

2. Add validation step to the pre-migration checklist:
```sql
-- Verify schema before deploying Debezium
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_schema='triage' AND table_name='outbox_events'
ORDER BY ordinal_position;
-- Expected columns: id, tenant_id, aggregate_type, aggregate_id, event_type, payload, created_at, published_at
```

3. Link the connector config to this schema in the design (currently implicit).

**Severity:** HIGH (silent connector failure if schema mismatch)

---

### MEDIUM Findings

#### **M1: S6.1 Code Generation Pipeline — `target: pyi` Misconfiguration**

**Location:** Section 2.3 (buf Configuration) — buf.gen.yaml

**Problem:**
The buf.gen.yaml specifies both `target: python` and `target: pyi`:
```yaml
outputs:
  - target: go-grpc
  - target: python
    out: gen/python
  - target: pyi
    out: gen/python
```

This configuration has issues:
1. **Unclear semantics:** Both outputs write to the same `gen/python` directory — will they collide or complement?
2. **Not standard buf pattern:** The typical approach is:
   - `python` generates `*_pb2.py` (implementation)
   - `pyi` generates `*_pb2.pyi` (type stubs)
   - Both write to same directory side-by-side
3. **CI/CD impact unclear:** The GitHub Actions workflow runs `buf generate` once but doesn't specify output order — if `pyi` overwrites `python`, stubs will replace implementation.

**Concrete Fix:**
Clarify the configuration with a comment and verify the GitHub Actions workflow:

```yaml
# buf.gen.yaml
outputs:
  - target: python
    out: gen/python
    opt:
      - "package_root=gen"
  # pyi target generates type stubs (.pyi files) to same directory
  # Both outputs (_pb2.py and _pb2.pyi) write to gen/python; they do NOT overwrite
  - target: pyi
    out: gen/python
```

And in the GitHub Actions workflow, commit both:
```yaml
- name: Generate and commit Protobuf code
  run: |
    buf generate packages/proto --template packages/proto/buf.gen.yaml
    git add gen/python/triage/
    git diff --cached --name-only  # Verify both .py and .pyi files
    git commit -m "chore: regenerate protobuf (Python stubs + implementation)"
```

**Severity:** MEDIUM (could break builds if not understood; CI/CD clarity issue)

---

#### **M2: S6.3 Idempotency Slow-Path Race Condition — Insert-First Atomicity Assumption**

**Location:** Section 4.1 — `_check_or_record_slow_path()` method

**Problem:**
The design uses an "insert-first" pattern with a UNIQUE constraint to detect duplicates:
```python
try:
    # Attempt INSERT (will fail if PK already exists)
    stmt = """INSERT INTO idempotency_records ... VALUES (...)"""
    await self.db_session.execute(stmt, {...})
except Exception as e:
    if "duplicate key" in str(e).lower():
        # Already processed
        return IdempotencyResult(is_duplicate=True)
```

Issues:
1. **Depends on UNIQUE constraint violation detection** — relies on DB-specific error messages ("duplicate key")
2. **No explicit conflict handling** — the code checks `str(e)` for "duplicate key" which is fragile and DB-agnostic only if using `ON CONFLICT DO UPDATE` syntax
3. **Database session state unclear** — after an exception, is the session still usable? (SQLAlchemy: yes, but not documented in design)
4. **Atomicity assumption:** The design assumes INSERT either succeeds or fails atomically, but if the network fails between INSERT and exception handler, the state is unknown

**Concrete Fix:**
Use PostgreSQL's native `ON CONFLICT` clause for truly atomic insert-or-fetch:

```python
async def _check_or_record_slow_path(
    self,
    tenant_id: str,
    event_id: str,
    event_type: str,
) -> IdempotencyResult:
    """Slow path: Postgres insert-first with ON CONFLICT for atomicity."""
    try:
        # Atomic insert-or-update using ON CONFLICT
        stmt = """
            INSERT INTO triage.idempotency_records 
              (tenant_id, event_id, event_type, result_json, processed_at)
            VALUES (:tenant_id, :event_id, :event_type, :result_json, :now)
            ON CONFLICT (tenant_id, event_id) DO UPDATE
              SET result_json = EXCLUDED.result_json
            RETURNING is_duplicate;  -- Custom column or logic to determine if this was a conflict
        """
        result = await self.db_session.execute(stmt, {...})
        # In PostgreSQL, ON CONFLICT never raises an error; it always succeeds
        # We need a way to detect if it was an INSERT vs UPDATE
        
        # Alternative: Use UPSERT with a sequence number to detect first insert
        # or manually check via INSERT...RETURNING xmax (PostgreSQL extension)
        
        return IdempotencyResult(is_duplicate=False)  # or True, depending on xmax
    except Exception as e:
        log.exception("idempotency_slow_path_error", error=str(e))
        return IdempotencyResult(is_duplicate=False, error=str(e))
```

Better yet, use a two-phase approach:
```python
# Phase 1: Try SELECT (fast path if exists)
SELECT result_json FROM idempotency_records WHERE tenant_id = ? AND event_id = ?;
# If found: is_duplicate=True, return cached result
# If NOT found: proceed to Phase 2

# Phase 2: Insert (atomic)
INSERT INTO idempotency_records (...) VALUES (...);
# If INSERT succeeds: is_duplicate=False, new event
# If INSERT fails with UNIQUE constraint: assume concurrent writer, retry Phase 1
```

**Severity:** MEDIUM (race condition edge case; unlikely but not documented)

---

#### **M3: S6.4 Worker Pool — Async Loop Exit Condition Ambiguous**

**Location:** Section 5.2 — `WorkerPool._worker_loop()` method

**Problem:**
The worker loop design:
```python
async def _worker_loop(self, worker_id: int) -> None:
    """Single worker loop."""
    while not self._stop:
        try:
            messages = await self.priority_queue.dequeue_message(...)
            if not messages:
                await asyncio.sleep(0.1)
                continue
```

Issues:
1. **Tight loop on empty queue:** If the queue is consistently empty, workers sleep 0.1s and retry. This wastes CPU cycles (100 iterations/sec) even when no work exists.
2. **No backoff escalation:** The sleep is fixed at 0.1s; it doesn't increase if the queue remains empty for minutes.
3. **Shutdown race condition:** When `WorkerPool.stop()` is called, it sets `_stop=True` and waits for tasks. But if a worker is in `dequeue_message()`, it may not see `_stop` until the dequeue completes. The 30s timeout in `stop()` may not be enough if `dequeue_message()` is slow.

**Concrete Fix:**
1. Add exponential backoff:
```python
async def _worker_loop(self, worker_id: int) -> None:
    backoff_ms = 100  # Start with 100ms
    max_backoff_ms = 5000  # Max 5s
    
    while not self._stop:
        try:
            messages = await self.priority_queue.dequeue_message(...)
            if not messages:
                await asyncio.sleep(backoff_ms / 1000)
                # Increase backoff exponentially
                backoff_ms = min(backoff_ms * 2, max_backoff_ms)
                continue
            
            # Reset backoff on successful dequeue
            backoff_ms = 100
            ...
```

2. Use a condition variable instead of polling:
```python
# In PriorityQueue
self.message_available = asyncio.Condition()

async def enqueue_message(...):
    await self.redis.zadd(...)
    async with self.message_available:
        self.message_available.notify()  # Wake waiting workers

# In _worker_loop
async with self.priority_queue.message_available:
    await self.priority_queue.message_available.wait()  # Sleep until notified
messages = await self.priority_queue.dequeue_message(...)
```

**Severity:** MEDIUM (efficiency issue; not functional correctness)

---

#### **M4: S6.5 Activities — Per-Activity Timeout Not Consistent Across All Activities**

**Location:** Section 6.2 (Activities — `classify_intent_activity` through `escalate_activity`)

**Problem:**
The design specifies different `start_to_close_timeout` values for each activity:
- `classify_intent_activity`: 60s (LLM calls)
- `extract_entities_activity`: 30s (rule-based)
- `make_decision_activity`: 10s (fast)
- ... (others specified)

But:
1. **No justification** for why 60s vs 30s vs 10s (other than "LLM calls are slow")
2. **No guidance** for on-call team if an activity times out (is 60s for LLM intentionally high, or should we reduce it?)
3. **Duplicate specification:** The workflow definition (6.1) also specifies timeouts; should they match? (They do, but not explicitly linked)
4. **Fallback behavior varies:** Some activities have `retry_policy`, others have graceful degradation (e.g., `retrieve_context` returns empty context on timeout), but this is not systematized

**Concrete Fix:**
Add a table documenting timeout rationale:

```markdown
### Activity Timeout Justification

| Activity | Timeout | Rationale | Fallback |
|----------|---------|-----------|----------|
| classify_intent | 60s | LLM inference; includes retry buffer | Timeout → escalate (don't fail workflow) |
| extract_entities | 30s | Rule-based regex; should be <5s but buffer for DB load | Timeout → empty entities; continue |
| make_decision | 10s | Pure logic; <100ms typical; buffer for GC pauses | Timeout → escalate (safety) |
| retrieve_context | 30s | Vector DB query + embedding lookup | Timeout → empty context; continue (graceful degradation) |
| generate_response | 60s | LLM generation; longest operation | Timeout → escalate (don't send bad response) |
| validate_output | 30s | Rule-based validation | Timeout → fail validation; escalate |
| execute_tools | 120s | External API calls (longest); includes retries | Timeout → escalate (don't retry tools) |
| escalate | 20s | Queue lookup + agent assignment | Timeout → assign to general queue |

Rationale for timeout selection:
- Activities that generate user-facing content (LLM) have high timeout but escalate on timeout
- Activities that retrieve data have moderate timeout and degrade gracefully
- Activities that make policy decisions have low timeout and escalate (conservative)
```

And update the code:
```python
ACTIVITY_TIMEOUTS = {
    "classify_intent": timedelta(seconds=60),     # LLM inference
    "extract_entities": timedelta(seconds=30),    # DB query + regex
    "make_decision": timedelta(seconds=10),       # Pure logic
    ...
}

# In workflow.run():
intent_result = await workflow.execute_activity(
    classify_intent_activity,
    state,
    start_to_close_timeout=ACTIVITY_TIMEOUTS["classify_intent"],
    retry_policy=retry_policy,
)
```

**Severity:** MEDIUM (clarity/maintainability; runtime impact if timeouts are too aggressive)

---

#### **M5: S6.6 Feature Flags — Mutual Exclusion Enforcement Not Testable**

**Location:** Section 7.1 — `EventAdapterSelector.select_adapter()` and integration in messages.py

**Problem:**
The design states:
> "Addresses H4: Enforces mutual exclusion so exactly ONE adapter (MVP or Kafka) processes each message, never both."

But the enforcement is:
1. **Only in application code** (the `ingest_message()` endpoint chooses one adapter)
2. **Not enforced at the infrastructure level** (both OutboxWriter and KafkaEventBus are running; if code is buggy, both will publish)
3. **No test explicitly verifies** "if this message goes through MVP, it doesn't also go through Kafka"
4. **No metrics/alarms** to detect if mutual exclusion is violated

**Concrete Fix:**
Add an integration test that verifies mutual exclusion:

```python
@pytest.mark.integration
async def test_message_ingestion_mutual_exclusion():
    """Test: message goes to exactly ONE adapter, never both."""
    message_id = "msg_123"
    tenant_id = "tenant_1"
    
    # Setup: feature flag 50% for Kafka
    await set_feature_flag("use_kafka_events", 50)
    
    # Track which adapters received the message
    mvp_received = []
    kafka_received = []
    
    # Patch OutboxWriter.write_event to track calls
    original_write_event = OutboxWriter.write_event
    async def tracked_write_event(*args, **kwargs):
        mvp_received.append(args)
        return await original_write_event(*args, **kwargs)
    OutboxWriter.write_event = tracked_write_event
    
    # Patch KafkaEventBus.publish to track calls
    original_publish = KafkaEventBus.publish
    async def tracked_publish(*args, **kwargs):
        kafka_received.append(args)
        return await original_publish(*args, **kwargs)
    KafkaEventBus.publish = tracked_publish
    
    # Ingest message
    await ingest_message({
        "message_id": message_id,
        "tenant_id": tenant_id,
        "channel": "email",
        "body": "Help!",
    })
    
    # Assert: exactly one adapter received the message
    assert len(mvp_received) + len(kafka_received) == 1, \
        f"Expected 1 adapter to receive message, got {len(mvp_received)} MVP + {len(kafka_received)} Kafka"
    
    # Restore
    OutboxWriter.write_event = original_write_event
    KafkaEventBus.publish = original_publish
```

Additionally, add a metric to the KafkaEventBus and OutboxWriter:
```python
# In KafkaEventBus.publish()
metrics.counter("event_published_kafka", tags={"tenant_id": tenant_id})

# In OutboxWriter.write_event()
metrics.counter("event_published_mvp", tags={"tenant_id": tenant_id})

# In monitoring: alert if (published_kafka + published_mvp) != total_ingested
```

**Severity:** MEDIUM (subtle bug potential; test gap)

---

#### **M6: S6.6 Parity Checker — Threshold Justification Missing**

**Location:** Section 7.2 — `ParityChecker` class

**Problem:**
The design specifies threshold constants:
```python
INTENT_DIVERGENCE_THRESHOLD = 0.02        # 2% of messages can have different intent
CONFIDENCE_THRESHOLD = 0.05               # 5% absolute difference acceptable
ENTITY_COUNT_THRESHOLD = 0.1              # 10% entity count difference acceptable
SUCCESS_RATE_THRESHOLD = 0.001            # 0.1% error rate difference
```

But provides **no justification**:
1. Why 2% divergence in intent? (Is this acceptable? What's the business impact?)
2. Why 5% confidence difference? (Does it matter if MVP gets 0.85 but Kafka gets 0.80?)
3. How were these thresholds chosen? (SLA targets? Risk tolerance?)

Without justification, on-call teams won't know if "intent divergence = 1.5%" is OK or a sign of a problem.

**Concrete Fix:**
Add a design rationale section:

```markdown
### Parity Threshold Justification

#### Intent Divergence (2%)
- Business Impact: Different intent classification → different response → user experience inconsistency
- Acceptable Range: 2% of messages (20 out of 1000)
- Reasoning: Classification models (MVP and Kafka using same underlying IntentClassifier) may differ slightly due to:
  - Different tokenization (if using different libraries)
  - Different preprocessing (Unicode normalization, case sensitivity)
  - Floating-point precision differences
  - 2% represents "models statistically equivalent" threshold (by ML standards)
- Action if exceeded: Pause cutover; investigate if models are configured differently

#### Confidence Threshold (5 percentage points)
- Business Impact: Confidence used to decide autonomy level (high confidence → allow autonomous, low → escalate)
- Acceptable Range: 5 percentage point difference (e.g., 0.85 vs 0.80 both OK)
- Reasoning: Confidence is used in binary decision (autonomy_level >= threshold). Small differences (<5pp) don't change decision outcome for most cases.
- Action if exceeded: Check if softmax/scaling differs between adapters

#### Entity Count Threshold (10%)
- Business Impact: Fewer entities → incomplete context for response generation
- Acceptable Range: 10% difference (e.g., 10 entities vs 9 entities OK; 10 vs 5 NOT OK)
- Reasoning: Entity extractor is deterministic (rules-based). Major divergence suggests misconfiguration.
- Action if exceeded: Verify RuleBasedEntityExtractor rules are identical in both adapter paths

#### Success Rate (0.1% error divergence)
- Business Impact: Errors should occur at same rate; if one adapter errors more, it's unreliable
- Acceptable Range: 0.1% difference (1 per 1000 messages)
- Reasoning: Both adapters use same underlying business logic; error rates should be nearly identical
- Action if exceeded: Investigate adapter-specific failure modes (Kafka timeout, Temporal service down, etc.)
```

**Severity:** MEDIUM (operational clarity; affects on-call decision-making)

---

## Missing Details (NIT-level but documented)

#### **N1: Docker Compose Missing Version Constraints**

**Location:** Section 8 — Infrastructure Topology (docker-compose.yml snippet)

The design shows service images without version pinning in some cases:
```yaml
kafka-broker-1:
  image: confluentinc/cp-kafka:7.5.0  # Pinned ✓
debezium-postgres-connector:
  image: debezium/connect:2.3.0       # Pinned ✓
temporal:
  image: temporalio/temporal:1.24.0   # Pinned ✓
```

Good pinning exists, but the document should explicitly note: "All image versions are pinned for reproducibility. If upgrading, test in staging first."

**Impact:** NIT (no functional issue; good practice reminder)

---

#### **N2: Testing Strategy — Time-Skipping Test for Temporal Not Detailed**

**Location:** Section 11 (Testing Strategy) — S6.5 Temporal testing

The design mentions:
> "time-skipping setup for Temporal"

But doesn't explain HOW to implement it. Temporal's time-skipping (advancing workflow clock without wall-clock delays) is powerful but requires:
- `TemporalServer.skip_time()`
- Test harness setup (specific SDK)
- May not work in production mode

**Recommendation:** Add a code snippet showing the test pattern:

```python
@pytest.mark.asyncio
async def test_workflow_with_time_skip():
    """Test workflow timeouts without waiting 60s."""
    client = await get_test_temporal_client()
    
    # Start workflow
    handle = await client.start_workflow(
        "ProcessMessageWorkflow",
        {...},
        id="test_wf_1",
    )
    
    # Time-skip 65s (simulate timeout after 60s)
    # (Temporal SDK provides this capability)
    await client.skip_time(timedelta(seconds=65))
    
    # Workflow should have timed out and escalated
    result = await handle.result()
    assert result["status"] == "escalated"
```

**Impact:** NIT (complexity; doesn't block implementation, just needs clarification)

---

## Summary Table

| ID | Severity | Section | Finding | Fix Type |
|---|----------|---------|---------|----------|
| H1 | HIGH | 3.2 | Debezium snapshot re-emission risk | Automate pre-flight check + fail deployment |
| H2 | HIGH | 3.2 | Debezium connector config field mapping unvalidated | Document schema DDL + add validation |
| M1 | MEDIUM | 2.3 | buf.gen.yaml pyi target misconfiguration | Clarify output handling in config + CI/CD |
| M2 | MEDIUM | 4.1 | Idempotency slow-path race condition | Use ON CONFLICT clause for atomicity |
| M3 | MEDIUM | 5.2 | Worker loop exit condition inefficient | Add exponential backoff or condition var |
| M4 | MEDIUM | 6.2 | Activity timeouts lack justification | Add timeout rationale table + documentation |
| M5 | MEDIUM | 7.1 | Mutual exclusion enforcement not tested | Add integration test + metrics |
| M6 | MEDIUM | 7.2 | Parity checker thresholds unjustified | Add threshold justification section |
| N1 | NIT | 8 | Docker Compose version pinning best practice | Add note on reproducibility |
| N2 | NIT | 11 | Time-skipping test pattern not detailed | Add code example |

---

## Conclusion

**The design is ARCHITECTURALLY SOUND** but requires **resolution of 2 HIGH + 4 MEDIUM findings** before implementation can proceed. The HIGH findings are **operational safety concerns** (Debezium configuration) that could silently cause data inconsistency. The MEDIUM findings are **clarity and test coverage gaps** that would hinder on-call operations and debugging.

**Recommended Next Steps:**
1. Address H1 + H2 with automated pre-flight checks (1–2 days)
2. Refine M1–M6 with clarifications and test cases (1–2 days)
3. Resubmit design for final approval
4. Proceed to implementation (S6.1 Protobuf generation, S6.2 Kafka adapter, etc.)

**Blocking Items:** H1, H2 must be resolved. M1–M6 should be resolved to avoid post-implementation rework.

