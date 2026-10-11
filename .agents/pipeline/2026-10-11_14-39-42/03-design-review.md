# Sprint 6 Design Review

**Reviewer:** Design Review Agent  
**Date:** 2026-10-11  
**Status:** CHANGES_REQUESTED  

---

## Findings

### HIGH Findings

#### 1. **Missing Directory Structure Verification (HIGH)**
**Location:** Section "S6 Directory Structure & Setup"  
**Issue:** The design specifies that "all directories listed above MUST be created and committed before implementation begins" but provides no verification that this actually happened. The pre-commit hook script is provided but never shown to have been executed or validated. Investigation shows:
- ✗ `packages/contracts/` does not exist
- ✗ `packages/py_contracts/` does not exist
- ✗ `packages/ts_contracts/` does not exist
- ✗ `services/event_bus/` does not exist
- ✗ `services/workflow_engine/` does not exist
- ✗ `infrastructure/debezium/` does not exist
- ✗ `packages/py_core/py_core/ports/` does not exist
- ✗ `packages/py_core/py_core/adapters/` does not exist

**Fix:** Add a section "Verified Directory Structure (Pre-Implementation Gate)" to the design document with:
1. Timestamp of verification execution
2. Output of pre-commit directory check script (from the design)
3. Explicit confirmation: "All required directories created and committed in commit ID: [hash]"
4. This section MUST be completed before code implementation begins.

**Verdict:** This is a blocking gate. Implementation cannot proceed without this verification in the design doc.

---

#### 2. **Unverified Outbox Table Schema (HIGH)**
**Location:** Section "Debezium CDC Relay > Outbox Table Verification"  
**Issue:** The design requires verification of the outbox table schema before Debezium configuration begins. The design states:

> "CRITICAL: Outbox table schema must be verified before implementation begins."

However, no verification is present in the document. Investigation of `services/api/src/triage/ingestion/outbox.py` shows:
- The existing `OutboxEvent` model is defined only in Python (no actual database table implementation shown)
- The `OutboxWriter.write_event()` method has a TODO: `# TODO: Write to database in same transaction as domain object`
- In-memory event storage is used: `self._in_memory_events: List[OutboxEvent] = []` with comment `# Demo mode`

**The actual Postgres outbox table is not yet created in the codebase.**

**Fix:** Before proceeding with Debezium, add to the design document a section "Verified Outbox Schema" with:
1. SQL query result showing current table structure
2. Comparison against expected schema in the design
3. If schema differs, update design SQL to match reality
4. Timestamp and who performed verification
5. If table does NOT exist yet, defer Debezium until S6.2 and note this explicitly in design assumptions

**Verdict:** This breaks the Debezium relay design. The SMT is configured to extract from `outbox.body`, but if the table structure differs or does not exist, Debezium configuration is incorrect.

---

### MEDIUM Findings

#### 1. **Ambiguous EventBus & WorkflowEngine Port Contracts (MEDIUM)**
**Location:** Sections "EventBus Port Definition" and "WorkflowEngine Port Definition"  
**Issue:** The design claims these are "NEW ports introduced in S6" with the statement:

> "CRITICAL CLARIFICATION: EventBus is a NEW port introduced in S6. There is no existing EventBus interface from Sprint 1 (S1)."

However, the actual contracts are:
- Incomplete Python Protocol definitions (no method stubs beyond `publish()` and `start_workflow()`)
- Missing error handling contract (what exceptions MUST be raised?)
- Missing idempotency contract for EventBus (idempotency key is mentioned in consumer layer, but EventBus itself has no contract)
- The design states outbox poller "wrapped as adapter in S6" but shows no actual OutboxPoller adapter class conforming to EventBus protocol

Investigation of source code shows `OutboxPoller` exists but it:
- Has no tenant context enforcement
- Has no error contract matching KafkaEventBus
- Is hardcoded to call registered handlers, not conforming to any standard EventBus interface

**Fix:** Clarify in the port definitions:
1. EventBus interface must include error contract: list ALL exception types (EventPublishError, MissingTenantContextError, ValidationError, etc.)
2. Add full Protocol method stubs with signatures and docstrings
3. Show OutboxPoller as concrete implementation of EventBus (not just "wrapped")
4. Add WorkflowEngine error contract: WorkflowExecutionError, WorkflowTimeoutException, MissingTenantContextError
5. Add statement: "EventBus and WorkflowEngine are adapter interfaces; both MVP and S6 adapters must conform to these contracts identically"

**Verdict:** Acceptance criteria #1, #9, #46 require contracts to pass "same contract suite from MVP" — but no such suite is provided, and the contract definitions are too vague to verify conformance.

---

#### 2. **Idempotency Key Derivation Underspecified (MEDIUM)**
**Location:** Sections "FR-KAFKA-IDEMPOTENCY-01" and subsection "Idempotency Keys"  
**Issue:** The design specifies `correlation_id` as the idempotency key, but:
1. Where does `correlation_id` come from? The design does not specify how EventBus assigns it.
2. Is `correlation_id` guaranteed to be unique PER EVENT across all tenants and all time?
3. The design uses format `idempotency:{tenant_id}:{correlation_id}` but states "correlation_id is stable and unique per event" without defining uniqueness boundary.

Acceptance criterion #27 states: "Idempotency key is extracted from event header (`correlation_id` field); test asserts key is identical across 3 retries" — but this does not define what correlation_id IS or how it's generated.

**Fix:** Add to FR-KAFKA-IDEMPOTENCY-01 a new subsection "Correlation ID Generation Contract" with:
1. Definition: "correlation_id is assigned by EventBus.publish() at publish time"
2. Uniqueness: "correlation_id MUST be globally unique (UUID v4 generated client-side before publish)"
3. Stability: "correlation_id does NOT change across retries, timeouts, or replays"
4. Example: `"correlation_id": "550e8400-e29b-41d4-a716-446655440000"`
5. Test: property test generates 1000 distinct events and verifies 0 duplicate correlation_ids

**Verdict:** Without this, idempotency guarantees are undefined. If two events arrive with the same correlation_id (due to client bug), the design provides no guidance on handling.

---

#### 3. **Parity Checker Comparison Semantics Undefined (MEDIUM)**
**Location:** Section "FR-CUTOVER-PLAN-01 > Parity Checker Logic"  
**Issue:** The design states:

> "After each event is processed by both pipelines, compare:
> - Event structure (envelope, payload, metadata) — must be byte-identical (after canonicalization).
> - Event ordering per tenant (partition) — must be identical offset-by-offset."

But "canonicalization" is never defined. What does byte-identical mean if timestamps differ by 1ms? The design mentions:

> "⚠ Parity warning: events differ in non-critical fields (e.g., timestamp diff > 1 s); log but do not alert."

**But the definition of "critical" vs. "non-critical" is not provided.** Acceptance criterion #59 states "Parity latency delta tracked" but does not define what delta is acceptable (2× old? 10×?).

**Fix:** Add to FR-CUTOVER-PLAN-01 a new subsection "Parity Comparison Rules (Detailed)" with:
```
Byte-identical fields (CRITICAL, must match exactly):
  - tenant_id
  - event_type
  - correlation_id
  - aggregate_id
  - Protobuf payload (binary)

Canonicalized fields (allowed to differ within tolerance):
  - timestamp: ≤ 1s difference (drift tolerance)
  - source field (may differ: "outbox-poller" vs. "debezium-kafka")
  - dlq reason (N/A for outbox, present for Kafka)

Non-critical fields (differences logged but not counted against parity threshold):
  - latency measurements
  - tracing headers (not in critical path)

Acceptance test:
  - 100 events published via both paths
  - Compare each pair
  - If critical fields differ, count as parity FAILURE
  - If canonicalized fields differ within tolerance, count as parity OK
  - Parity score = (OK + canonicalized_within_tolerance) / 100
  - Criterion: parity score ≥ 99.5%
```

**Verdict:** The parity checker code cannot be written without this specification; test criteria #58–60 are vague.

---

#### 4. **Activity Timeout Documentation Missing Concrete Mappings (MEDIUM)**
**Location:** Section "Temporal Adapter > Activity Definitions" and acceptance criterion #51  
**Issue:** The design includes a table of timeouts for 5 activities (classify, retrieve, compose, guard, assign) with example values (30s, 45s, 60s, etc.), but:
1. These are hypothetical examples, not measured values
2. No profiling data or rationale provided for the specific timeout values
3. Criterion #51 states "Every activity has timeout documentation in docstring" but the design only shows an EXAMPLE docstring for `classify_intent`; no actual implementation provided
4. The design defers timeout tuning to "S6 profiling" but does not block on this — what if tuning shows 30s is too short?

**Fix:** Add to FR-WORKFLOW-ENGINE-01 a section "Activity Timeout Tuning (Stage Gate)" with:
1. Statement: "Timeout values in the table above are ESTIMATES. Actual timeouts MUST be tuned via load testing."
2. Load test procedure: "Run k6 test with 100 concurrent triage requests; measure p50, p95, p99 latency per activity"
3. Tuning rule: "Set schedule_to_close_timeout = p99 latency × 1.25 (25% buffer); start_to_close_timeout = p99 latency × 1.1"
4. Acceptance: "Load test completed; timeout values approved by SRE before production deployment"
5. Contingency: "If any activity consistently exceeds its timeout during load test, escalate to tech lead for design review"

**Verdict:** Without this, S6 implementation will use guessed timeouts, leading to timeouts in production. Criterion #51 is not verifiable against estimates.

---

#### 5. **DLQ Replay Rate Limiting Not Enforced in Code (MEDIUM)**
**Location:** Section "Dead Letter Queue & Replay Tooling > Replay Tooling > Rate limiting"  
**Issue:** The design specifies rate limiting as:

```python
REPLAY_RATE_LIMIT = 10  # events/second
```

And acceptance criterion #35 states: "Replay rate-limiting enforced: > 10/s triggers backpressure; test verifies via property test."

However:
1. The design code snippet shows a basic sleep loop but does NOT show backpressure (queuing) behavior
2. "Backpressure" is mentioned in acceptance criteria but never defined; does it mean rejection, queueing, or slowing?
3. No timeout or queue overflow behavior specified — what if replaying 1M events? Will it queue indefinitely?

**Fix:** Add to FR-KAFKA-DLQ-01 a subsection "Replay Rate-Limiting & Backpressure Semantics" with:
```
Rate limit: maximum 10 events/second per DLQ replay operation

Backpressure behavior:
  - If replay rate exceeds 10/s, publish calls are delayed (throttled) not rejected
  - Delay = (number_of_events / 10) seconds minimum
  - Example: replaying 1000 events takes minimum 100 seconds
  - Client sees blocking call (await publish_to_original_topic(event) sleeps)
  - No queuing; backpressure is inline

Timeout: if replay takes > 1 hour for 1M events, client can cancel (cancel token)
  - If cancelled, audit log records: replay_id, cancelled_at, events_published_before_cancel

Acceptance test:
  - Call replay() with 20 events concurrently
  - Measure time: should take ≥ 2 seconds (20 events / 10 per sec)
  - Verify no events are dropped (all 20 published to original topic)
```

**Verdict:** Criterion #35 cannot be verified; "property test with concurrent replay calls" is undefined (how many concurrent calls? do they contend for rate limit? how is "backpressure" measured?).

---

#### 6. **Consumer Idempotency Fallback Behavior for Postgres Timeout Undefined (MEDIUM)**
**Location:** Section "Consumer Idempotency Layer > Timeout & Retry Semantics"  
**Issue:** The design states for Postgres timeout:

> "If Postgres INSERT or SELECT times out or connection drops:
> - **Fail the event immediately; send to DLQ with reason `"idempotency_postgres_unavailable"`**
> - Do NOT attempt to process the event (fail-closed, not optimistic)"

But this creates a chain reaction: if Postgres is down, ALL events go to DLQ. The design then says:

> "On-call can replay from DLQ once Postgres recovers"

However:
1. No mention of how long Postgres can be down (SLA)
2. No mention of how many events can accumulate in DLQ before alerts trigger
3. The design does NOT show how to DETECT that Postgres is back before manual replay (is there an automated retry probe?)
4. Acceptance criterion #23 requires "Redis fast path: idempotent; second write succeeds" but if Postgres is down AND Redis is down, there is NO safe fallback

**Fix:** Add to FR-KAFKA-IDEMPOTENCY-01 a subsection "Postgres Unavailability Handling" with:
```
Postgres downtime SLA: If Postgres is down > 5 minutes, page on-call

Behavior during outage:
  - Events failing idempotency check are sent to DLQ with reason "idempotency_postgres_unavailable"
  - DLQ has separate consumer (or topic) for error handling
  - Alert: if DLQ event rate > 10/sec for > 1 min, escalate (indicates systematic Postgres failure)

Recovery process:
  - On-call restores Postgres (outside this design)
  - On-call runs: triage-cli dlq replay --reason postgres-recovered --all-in-range [time] [time]
  - Replay consumes events from DLQ, re-publishes to original topics
  - Idempotency dedup ensures exactly-once: if already processed during Postgres recovery, skip

Contingency: if Postgres AND Redis both unavailable for > 5 minutes:
  - Manual intervention required
  - Drain queues (stop consuming)
  - Alert on-call for disaster recovery procedure (outside S6 scope)
```

**Verdict:** Criterion #25 states "Redis unavailable → event still idempotent via Postgres (integration test)" but does NOT handle Postgres unavailability; the design is incomplete.

---

### NIT Findings

#### 1. **Proto Comments Format Inconsistency (NIT)**
**Location:** Section "Protobuf Field Validation"  
**Issue:** Proto comments show OpenAPI 3.1 format examples like `// required: tenant_id must be non-empty UUID` and `// pattern: ^[0-9a-f]...`, but the examples use inconsistent capitalization and spacing. Some fields show `// required:`, others show `// optional:`.

**Fix:** Standardize all proto comments to a single format. Example:
```proto
string tenant_id = 1;
  // @required: must be non-empty UUID
  // @pattern: ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$
  // @maxLength: 36
  // @example: "550e8400-e29b-41d4-a716-446655440000"
```

**Verdict:** Minor stylistic; does not block implementation but improves consistency.

---

#### 2. **Temporal Workflow Example Incomplete (NIT)**
**Location:** Section "Temporal Adapter > Workflow Orchestration"  
**Issue:** The workflow example in the design is cut off mid-code:

```python
        except ActivityFailureException as e:
            logger.error(f"Activity failed", error=str(e), workflow_id=workflow.info().workflow_id)
            r
```

The error handling for `ActivityFailureException` is incomplete and doesn't show how the workflow returns a failed result or what happens to the event.

**Fix:** Complete the example:
```python
        except ActivityFailureException as e:
            logger.error(f"Activity failed", error=str(e), workflow_id=workflow.info().workflow_id)
            return {
                "status": "failed",
                "error_code": str(type(e).__name__),
                "error_message": str(e),
            }
```

**Verdict:** Minor; does not affect correctness but the incomplete example is confusing.

---

#### 3. **Feature Flag State Machine Diagram Missing (NIT)**
**Location:** Section "FR-CUTOVER-PLAN-01"  
**Issue:** The design references "dual-adapter mode" and mixed flag states (Kafka on, Temporal off) but does not provide a state diagram or table showing all valid flag combinations and their behavior.

**Fix:** Add a table:
```
| EVENT_BACKBONE_KAFKA | WORKFLOW_ENGINE_TEMPORAL | Behavior | Adapter Used |
|---|---|---|---|
| false | false | MVP mode | OutboxPoller, InProcessExecutor |
| true | true | S6 mode (production) | KafkaEventBus, TemporalWorkflowEngine |
| true | false | Mixed (staging test) | KafkaEventBus, InProcessExecutor |
| false | true | Mixed (staging test) | OutboxPoller, TemporalWorkflowEngine |
```

**Verdict:** Minor; helpful for clarity but not blocking.

---

## Verified Assumptions

1. ✓ **Sprint 1 (MVP) has delivered outbox poller and in-process executor** — code found in `services/api/src/triage/ingestion/outbox.py` (though implementation is incomplete with TODOs)
2. ✓ **Kafka and Temporal are "available in staging"** — design assumes these are already deployed; not verified but stated as assumption
3. ✓ **Protobuf code generation via buf is feasible** — buf is a standard tool; no blockers
4. ✓ **Python Protocol-based ports are appropriate for S6** — Python 3.10+ supports Protocol; matches existing codebase
5. ✓ **Redis and Postgres are available for idempotency** — design references existing Postgres; Redis is deployable

---

## Unverified / Wrong Assumptions

1. ✗ **"Outbox table exists with schema [X]"** — No Postgres table verified. Python OutboxEvent model exists but no corresponding table created. Debezium connector configuration assumes table exists; this will fail at runtime.
   
2. ✗ **"EventBus and WorkflowEngine interfaces from S1"** — Design correctly states these are NEW in S6, but the claim "there is no existing EventBus interface from Sprint 1" contradicts the earlier statement that "KafkaEventBus adapter conforms to the existing EventBus interface from MVP (S1.9)". This is internally contradictory.

3. ✗ **"buf breaking CI check enforces backward compatibility"** — Design assumes buf is integrated into CI. No CI workflow shown; no confirmation buf check is running on PRs.

4. ✗ **"Temporal cluster is available in staging"** — Assumption stated but not verified. Docker compose or managed service deployment is not confirmed.

5. ✗ **"Replication slot 'triage_slot' can be created by Alembic migration"** — Design states this but Postgres replication slots require WAL configuration and special privileges. No migration shown; assumes Postgres is in "logical" decoding mode already.

---

## Summary

**Verdict: CHANGES_REQUESTED**

**Blocking Issues (must fix before implementation):**
1. **HIGH #1**: Directory structure verification missing from design document
2. **HIGH #2**: Outbox table schema verification missing and table not found in codebase
3. **MEDIUM #1**: EventBus and WorkflowEngine contracts incomplete (missing error contract, exception types)

**Issues to Clarify (should fix before widespread implementation):**
1. **MEDIUM #2**: Correlation ID generation contract undefined
2. **MEDIUM #3**: Parity comparison semantics vague ("canonicalization", critical vs. non-critical fields)
3. **MEDIUM #4**: Activity timeout values are estimates, tuning process undefined
4. **MEDIUM #5**: DLQ replay backpressure semantics incomplete
5. **MEDIUM #6**: Postgres downtime handling incomplete; cascading failure risk

**Minor Improvements (can proceed, but should fix):**
1. **NIT #1**: Proto comment format inconsistency
2. **NIT #2**: Temporal workflow example incomplete
3. **NIT #3**: Feature flag state machine diagram missing

---

## Recommendation

**Do not start Sprint 6 implementation until:**
1. Pre-implementation gate (directory structure check) is added to design and executed
2. Outbox table schema is verified or created; result added to design
3. EventBus and WorkflowEngine port contracts are completed with error types and exception handling
4. HIGH findings are resolved

**The design is well-structured and comprehensive, but lacks concrete grounding in the existing codebase. The verification sections (outbox schema, directory structure) are the most critical gates.**
