# Sprint 6 Requirements: Event Backbone & Durable Workflows

**Document Version:** 1.0  
**Sprint:** S6 (Stage 2, Week 1–2)  
**Date:** October 2026  
**Owner:** Engineering Team  
**Status:** Ready for design review  

---

## Summary

Sprint 6 transitions the MVP's transactional outbox pattern into a production-scale event backbone powered by Kafka + Debezium and replaces the in-process workflow executor with Temporal durable workflows. The sprint delivers **6 Protobuf contract files** with buf validation, **3 adapters** (EventBus, WorkflowEngine with idempotency), **consumer-side idempotency** on Redis and Postgres paths, **DLQ + replay tooling**, **priority lanes** for chat vs. email message ordering, and a **cutover plan with parity verification**. All changes remain behind feature flags and are verified in staging before production deployment. Upon completion, Kafka and Temporal become the default backbone for event durability and write-action orchestration, enabling the remaining Stage 2 sprints (S7–S11) to build policy, approvals, ML pipelines, and operational readiness on a resilient foundation.

This sprint addresses **2 HIGH + 4 MEDIUM design findings** from the technical design review: snapshot safety in the Protobuf schema, field validation thresholds, idempotency race conditions in consumer retry logic, worker pool efficiency under load, activity timeout documentation, feature flag test coverage, and parity threshold tuning. Requirements are scaled to the complexity of a production infrastructure lift and include concrete acceptance criteria tied to contract validation, property testing, and integration scenarios.

**Assumptions:**
- Stage 1 (MVP) has shipped successfully with the outbox poller and in-process executor.
- Kafka (KRaft mode) and Temporal clusters are available in the staging environment for integration testing.
- Design review findings are either addressed in code, covered by tests, or explicitly deferred with justification.
- All proto-generated code remains type-safe and gated by `buf breaking` CI checks.
- Cutover from outbox → Debezium happens behind a `EVENT_BACKBONE_KAFKA` feature flag, with both adapters running in parallel in staging for ≥1 week before production activation.

---

## Functional Requirements

### FR-PROTO-01: Protobuf Contract Definitions
**Tier:** Contract-First (Tier B)  
**Definition of Done:**
- 6 Protobuf files in `packages/contracts/proto/`: 
  - `events.proto` — base `Event` message (aggregate root, event name, timestamp, tenant_id, correlation_id, causation_id, user_context)
  - `messages.proto` — message ingestion events (`MessageIngested`, `MessageCoalesced`, `MessageFailed`)
  - `workflow_inputs.proto` — workflow start and activity input envelopes (`WorkflowStarted`, `ActivityScheduled`, `ActivityCompleted`)
  - `triage_events.proto` — triage lifecycle events (`TriageRunStarted`, `TriageNodeExecuted`, `TriageDecisionMade`, `TriageRunCompleted`)
  - `action_events.proto` — action workflow events (`ActionProposed`, `ActionPolicyGated`, `ActionApprovalRequested`, `ActionExecuting`, `ActionSucceeded`, `ActionFailed`, `ActionCompensating`)
  - `schema_registry.proto` — metadata for Schema Registry integration (version, compatibility mode, namespace)
- All messages use `repeated` fields for traceability (e.g., policy checks, guard results) rather than nested oneof to preserve backward compatibility.
- `buf breaking` CLI validates BACKWARD_TRANSITIVE compatibility on every PR.
- Generated Python code (pyright/mypy strict) in `py_contracts` module; generated TypeScript (tsc strict) in `ts_contracts` package.
- Optional fields explicitly marked `optional` (proto3 syntax ≥ 1.12) to prevent snapshot ambiguity (HIGH finding address: #1).
- Custom validation rules embedded in proto comments (OpenAPI 3.1 format) for downstream Schema Registry migration (e.g., `// required: tenant_id must match current context`).
- Round-trip serialization tests for all 6 files: serialize → deserialize → assert equality.
- Dependency graph: events ← messages, triage_events, action_events; all depend on schema_registry.

**Acceptance Criteria:**
1. ✓ All 6 proto files compile without errors under `buf build`.
2. ✓ `buf breaking` passes when compared against committed `buf.yaml` lock file.
3. ✓ Generated Python type stubs pass `pyright --strict` and imports work in `py_core.event`.
4. ✓ Generated TypeScript compiles with `tsc --strict` and exports named types.
5. ✓ Round-trip test: for each message type, serialize via `SerializeToString()` → deserialize → field-by-field equality (pytest parametrized, 6 messages × 3 variants = 18 test cases).
6. ✓ Backward-compatibility constraint: removing any optional field fails `buf breaking` CI check.
7. ✓ Proto comments include OpenAPI validation hints (`required`, `pattern`, `minLength`, `maxLength`) for 100% of scalar fields.
8. ✓ No `oneof` fields used; traceability arrays used instead (MEDIUM finding #1 address).

---

### FR-EVENTBUS-01: Kafka Adapter for EventBus Port
**Tier:** Contract-First (Tier B)  
**Definition of Done:**
- Implement `KafkaEventBus` adapter in `services/event_bus/adapters/kafka_adapter.py` conforming to the existing `EventBus` interface from MVP (S1.9).
- **CloudEvents envelope:** every event wrapped in CloudEvents 1.0 format (RFC 9222) with:
  - `specversion` = "1.0"
  - `type` = "{domain}.{entity}.{action}" (e.g., "triage.message.ingested")
  - `source` = "urn:triage:{service_name}:{instance_id}"
  - `id` = {correlation_id} (unique per event)
  - `time` = ISO 8601 UTC
  - `datacontenttype` = "application/protobuf"
  - `subject` = "{tenant_id}:{aggregate_root_id}"
  - **Extensions:** `tenantid`, `causationid`, `userid`, `idempotencykey` (all required for replay)
  - Protobuf binary payload (not JSON to preserve performance).
- **Partition key strategy:** `{tenant_id}` (strict requirement: all events from one tenant land on the same partition for ordering). Routing key selection logged at TRACE level for debugging.
- **Producer configuration:** 
  - Acks = "all" (wait for leader + all in-sync replicas).
  - Retries = 3 (exponential backoff 100–3000 ms).
  - Compression = "snappy".
  - Batch size = 16 KB, linger = 100 ms.
  - Idempotence enabled (enable.idempotence = true, max.in.flight.requests = 5).
- **Topic naming convention:** `triage.{event_domain}.{env}` (e.g., `triage.messages.staging`, `triage.triage.staging`).
  - Topics auto-created if they do not exist (or pre-created by IaC with retention = 7 days).
  - Replication factor ≥ 2 (staging) / ≥ 3 (production).
- **Tenant isolation:** context must be set before publish; missing or mismatched tenant_id raises ValueError with fail-closed behavior.
- **Error handling:**
  - Failed produce (network, broker down, timeout) → retry 3 times, then raise `EventPublishError(retriable=False)` to surface to the outbox writer (which will retry the whole row).
  - Timeout ≥ 30 s per produce call (to allow Kafka recovery).
- **Metrics published** (OpenTelemetry):
  - `event_bus.kafka.published_total{tenant_id,event_type}` (counter).
  - `event_bus.kafka.publish_latency_ms{tenant_id,event_type}` (histogram, P50/P95/P99).
  - `event_bus.kafka.publish_errors_total{tenant_id,event_type,error_code}` (counter).

**Acceptance Criteria:**
1. ✓ `KafkaEventBus` class passes the **same event-bus contract suite** from MVP (S1.9) when running against Testcontainers Redpanda or Kafka: at-least-once delivery, per-tenant ordering, consumer deduplication.
2. ✓ CloudEvents envelope is RFC 9222 compliant; schema validation against CloudEvents JSON Schema (cf. https://spec.cloudevents.io/v1.0/schema/core.json).
3. ✓ Partition key is always `{tenant_id}`; no event lands on a partition that would be read by a different tenant (isolation property test).
4. ✓ Produces with acks="all"; if broker is down, produce raises EventPublishError within 30 s.
5. ✓ Published event round-trips through Kafka and deserializes correctly; Protobuf envelope intact.
6. ✓ Metrics are emitted on every publish attempt (success and failure); Prometheus scrape contains all three counters + histogram.
7. ✓ Tenant context mismatch test: `set_context(tenant_id="A")` then publish with event.tenant_id="B" raises ValueError before sending.
8. ✓ At least one contract test runs against Redpanda (faster in test environments) and one against Kafka (production-like), both pass identically.

---

### FR-EVENTBUS-02: Kafka + Debezium Outbox Relay Migration
**Tier:** Contract-First (Tier B)  
**Definition of Done:**
- Deploy Debezium Postgres CDC connector + SMT (Single Message Transform) in staging (not MVP's direct poller).
- Connector configuration in `infrastructure/debezium/postgres-connector.json`:
  - Plugin = "io.debezium.connector.postgresql.PostgresConnector"
  - Logical decoding slot = `triage_slot` (replication slot must exist in Postgres; created by Alembic migration).
  - Table = `triage.outbox` (same MVP table).
  - Transforms = `RouteByAggregate` (routes events to `triage.{aggregate_type}.{env}` topics).
  - Key extractor = `tenant_id,aggregate_id` (for partition assignment).
  - Value converter = Proto (via Confluent Schema Registry with `value.converter.schema.registry.url`).
  - Poll interval = 1000 ms; batch.size = 2048.
- **Schema Registry integration:**
  - All published events registered in Confluent Schema Registry with `BACKWARD_TRANSITIVE` compatibility.
  - Subject naming = `triage.{event_domain}.{env}-value` (Confluent default).
  - Avro schema auto-generated from Protobuf definitions by buf plugin (or hand-crafted to match proto structure).
  - Schema version incremented on proto `buf breaking` violations caught before deployment.
- **Change Data Capture (CDC) schema:** CDC payload includes before/after, op (I/U/D), ts_ms (Postgres WAL timestamp), and the `outbox` row itself.
- **Transformation rules:**
  - Extract event (value column) from `outbox.body` (encrypted Protobuf, decrypted before SMT).
  - Wrap in CloudEvents envelope (using outbox row metadata: id, aggregate_id, tenant_id, occurred_at, etc.).
  - Drop the CDC metadata after transformation.
  - Filter: only INSERTs into outbox are forwarded (no UPDATEs or DELETEs; the table has delete triggers that prevent these).
- **Initial snapshot:**
  - Debezium snapshot.mode = "never" in staging (production will use "initial_only" with fast forward after snapshot).
  - Existing outbox rows (if any) are NOT replayed at cutover (MEDIUM finding #2 address: snapshot safety — existing rows marked as processed before enabling Debezium).
  - Cutover process: drain outbox poller, mark all outbox rows as processed, enable Debezium, verify no gaps.
- **Postgres prerequisites:**
  - `wal_level = logical` (production setting).
  - Replication slot `triage_slot` exists and is monitored for lag (alert if > 1 GB retained WAL).
  - User `debezium` has REPLICATION privilege.

**Acceptance Criteria:**
1. ✓ Debezium connector deploys to Kafka Connect cluster in staging without errors.
2. ✓ First outbox INSERT propagates to Kafka topic within 5 s.
3. ✓ CDC payload deserializes as valid CloudEvents; tenant_id and event_id extracted correctly.
4. ✓ Transformed event matches the structure of an event published by `KafkaEventBus` (same CloudEvents envelope, same Protobuf payload).
5. ✓ Schema Registry contains ≥ 1 schema per event type; `buf breaking` blocks backward-incompatible schema uploads.
6. ✓ Cutover test in staging: old poller and Debezium run in parallel for 1 week; parity checker confirms identical events (see FR-PARITY-01).
7. ✓ Snapshot handling: after initial Debezium startup, exactly 0 duplicate events from pre-cutover outbox rows.
8. ✓ Replication slot lag monitored; alert fires if lag > 1 GB; lag is cleared within 1 h of manual remediation.

---

### FR-KAFKA-IDEMPOTENCY-01: Consumer-Side Idempotency with Redis + Postgres Paths
**Tier:** Contract-First (Tier B) + Tier A (unit tests)  
**Definition of Done:**
- **Idempotency strategy:** detect duplicate events by `{correlation_id}` (Kafka offset alone is insufficient because of rebalancing/replay).
  - Offset is used as a secondary key to detect Kafka broker rebalancing; if offset moves backward for the same correlation_id, it is a replay.
- **Fast path (Redis):** store `correlation_id → processed_at` in Redis with TTL = 7 days (matches event retention in Kafka).
  - Set operation: `SET idempotency:{correlation_id} 1 EX 604800` (atomic).
  - Check: `EXISTS idempotency:{correlation_id}` (O(1), ≤ 1 ms).
  - Sharded across tenants: Redis key includes tenant_id to avoid collisions: `idempotency:{tenant_id}:{correlation_id}`.
  - If Redis is unavailable, fall through to Postgres path (not fail-closed; the fallback is the safety mechanism).
- **Slow path (Postgres):** `processed_events` table for critical paths (action workflows, write tools, policy decisions) and as Redis backup:
  - Columns: `tenant_id, correlation_id, event_id, event_type, processed_at, processor_name, idempotent_result` (optional JSON).
  - Natural key: `(tenant_id, correlation_id)` with unique constraint.
  - Insert on first processing; upsert key returns duplicate key error if already processed.
  - Idempotent result stored if present (e.g., action execution result, so replay returns the same result).
  - TTL job (Alembic migration, runs weekly): delete rows older than 90 days.
- **Retry logic with idempotency key stability (MEDIUM finding #3 address):**
  - Idempotency key MUST be deterministic and stable across retries (e.g., derived from event id, not wall-clock time or random UUIDs).
  - Idempotency key collision during concurrent retries: first writer wins (CAS semantics in Postgres; Redis SET with NX flag).
  - Test: property test with Hypothesis simulating concurrent retries of the same event; verify exactly-once execution.
  - If retry changes the idempotency key (e.g., adds a timestamp), it is treated as a new event (risk: duplicate processing); this is flagged in code review.
- **DLQ behavior on idempotency mismatch:**
  - If Postgres result differs from Redis result (cache inconsistency), log warning, trust Postgres (the source of truth), do not replay to DLQ.
  - If idempotency key lookup times out, retry immediately (exponential backoff, max 3 attempts), then DLQ.

**Acceptance Criteria:**
1. ✓ Redis SET is idempotent: writing the same correlation_id twice returns success; second write does not raise error.
2. ✓ Postgres unique constraint enforces exactly-one row per `(tenant_id, correlation_id)` pair; duplicate insert raises IntegrityError, which is caught and converted to "already processed" log.
3. ✓ Fallback test: disable Redis, verify event is still idempotent via Postgres (integration test).
4. ✓ Property test: generate 100 concurrent duplicate-event deliveries; verify exactly 1 business-logic execution (e.g., exactly 1 Stripe refund call).
5. ✓ Idempotency key is extracted from event header (`correlation_id` field); test asserts key is identical across 3 retries.
6. ✓ Cached result matches Postgres result; for action workflows, stored result is returned on replay (not re-executed).
7. ✓ TTL job runs weekly (scheduled task in Temporal or via pg_cron); rows older than 90 days are deleted.
8. ✓ Postgres result column stores JSON serialized outcome; deserialization test confirms structure is valid.

---

### FR-KAFKA-DLQ-01: Dead Letter Queue & Replay Tooling
**Tier:** Tier A (unit tests) + Tier B (contract for replay)  
**Definition of Done:**
- **DLQ topic:** `triage.dlq.{env}` with retention = 30 days (longer than active topics for investigation).
- **DLQ trigger:** after 3 retries (exponential backoff: 1 s, 10 s, 100 s) a message fails its consumer handler, it is:
  - Logged at ERROR level with full event context.
  - Serialized as-is (original CloudEvents envelope + Protobuf payload).
  - Published to DLQ with a new envelope field `dlq_reason` (string), `dlq_retry_count` (int), and `dlq_timestamp` (UTC).
  - Original tenant_id preserved in partition key (so DLQ events are also sharded by tenant).
- **DLQ consumer (admin tool):** CLI or console UI to:
  - List DLQ events by date range, tenant, event type, error type.
  - Inspect full event payload (Protobuf decoded).
  - **Replay:** select N events and re-publish to the original topic (with original correlation_id and offset; Kafka treats this as a new message, but idempotency deduplication saves it).
  - Replay audit: record who, when, how many, which events (immutable audit log row).
- **Replay safety:**
  - Replay is **idempotent** by design (via idempotency key): replaying an event already processed is a no-op (no duplicate action).
  - Replay rate-limited: max 10/s per worker to avoid overwhelming the consumer group.
  - Replay creates a new offset in the topic; old offset is never re-read.
- **Observability:**
  - Metric: `kafka.dlq.events_total{tenant_id,error_type}` (counter).
  - Dashboard: DLQ events by hour, top error types, replay history.

**Acceptance Criteria:**
1. ✓ After 3 failed retries, event is published to DLQ (not dropped).
2. ✓ DLQ event retains original correlation_id, event_type, tenant_id, and adds dlq_reason, dlq_retry_count, dlq_timestamp.
3. ✓ Replay CLI: `triage-cli dlq replay --topic triage.messages.staging --start 2026-10-01 --end 2026-10-02 --tenant acme` lists events in date range.
4. ✓ Replayed event is re-published to original topic; consumer processes it; if already processed (by idempotency key), it is skipped and logged as idempotent skip.
5. ✓ Replay is recorded in audit log: `events_audit` table with columns `dlq_replay_id, replayed_by_user_id, replayed_at, event_count, replay_scope (date_range|tenant_id)`.
6. ✓ Replay rate-limiting: if 10+ replays/s are attempted, subsequent requests queue or fail with backpressure message (test via property test with concurrent replay calls).
7. ✓ DLQ retention policy: events older than 30 days are automatically deleted by Kafka (verified via retention test).
8. ✓ Metrics emitted on DLQ publish; Prometheus scrape shows counter incremented.

---

### FR-PRIORITY-LANES-01: Chat vs. Email Consumer Groups (Priority & Starvation Prevention)
**Tier:** Tier A (unit tests)  
**Definition of Done:**
- **Consumer group architecture:** two Kafka consumer groups within the same cluster, both reading from `triage.messages.{env}`:
  - Group `triage-workers-chat` (≤ 10 consumers in prod, processes only chat messages).
  - Group `triage-workers-email` (≤ 5 consumers in prod, processes only email messages).
  - Both groups read from the same topic but filter by `message_type` field in CloudEvents extension or Protobuf payload.
- **Filtering logic:** on consumer receive, check event type:
  - `message_type == "chat"` → assign to chat lane.
  - `message_type == "email"` → assign to email lane.
  - Other types (e.g., system events, not yet classified) → default lane (email, non-blocking).
- **Queue isolation:**
  - Chat messages are processed with P95 latency SLO ≤ 2 s (time from publish to completion).
  - Email messages are processed with P95 latency SLO ≤ 60 s (batched, lower priority).
  - If email processing is slow, chat processing is NOT starved (separate thread pools / processes).
- **Worker pool configuration (MEDIUM finding #4 address: worker pool efficiency):**
  - Chat workers: thread pool size = 20 (high concurrency, chat is latency-sensitive).
  - Email workers: thread pool size = 5 (lower concurrency, email is batch-oriented).
  - Both pools have queue length monitoring; alert if queue depth > 50% capacity.
  - Backpressure: if queue is full, consumer pauses polling (Kafka API: `consumer.pause(partitions)`).
- **Starvation prevention:**
  - Every 5 minutes, check email backlog size; if > N messages (N = 100), temporarily boost email workers to 8 (up from 5) for 15 minutes.
  - This is a heuristic; Temporal tasks (S7) will provide a more sophisticated load-aware routing.
- **Observability:**
  - Metrics: `kafka.chat_lane.latency_ms{tenant_id}` (histogram), `kafka.email_lane.latency_ms{tenant_id}`, `kafka.*_lane.queue_depth{tenant_id}` (gauge).
  - Alert: if email queue depth > 100 for > 10 min, page on-call.

**Acceptance Criteria:**
1. ✓ Two consumer groups exist in Kafka; `kafka-consumer-groups` CLI shows both subscribed to `triage.messages.{env}`.
2. ✓ Events are correctly routed to lane: test publishes 10 chat + 10 email messages; consumer threads are tagged by lane; all chat are processed by chat lane, all email by email.
3. ✓ Chat latency SLO (P95 ≤ 2 s) is met under normal load (integration test with k6 submitting 20 chat msgs/s for 2 min).
4. ✓ Email latency SLO (P95 ≤ 60 s) is met under normal load.
5. ✓ Starvation test: generate 100 email messages and 5 chat messages concurrently; chat messages are processed within 2 s, even though email queue is growing. Test succeeds if chat latency is ≤ 2 s while email is still processing.
6. ✓ Worker pool sizes are configurable via environment variables; test runs with chat=20, email=5; metrics report pool size.
7. ✓ Email backlog boost heuristic: after generating 150 email messages, verify email worker count increases from 5 to 8 for 15 min (via metrics or logs), then decreases back to 5.
8. ✓ Metrics are emitted for both lanes; Prometheus scrape shows all four metrics (latency, queue_depth) for both chat and email.

---

### FR-WORKFLOW-ENGINE-01: Temporal Adapter for WorkflowEngine Port
**Tier:** Contract-First (Tier B) + Tier A (unit tests)  
**Definition of Done:**
- Implement `TemporalWorkflowEngine` adapter in `services/workflow_engine/adapters/temporal_adapter.py` conforming to the existing `WorkflowEngine` interface from MVP (S1 in-process executor).
- **Workflow ID assignment:** MUST be deterministic; use `sha256(tenant_id|conversation_id|run_id)` (or idempotency key if already available from the message).
  - Test: same input always produces same Workflow ID.
  - Prevents duplicate workflow starts (Temporal's idempotency key).
- **Workflow execution:**
  - Start workflow via `client.start_workflow(workflow_name, workflow_id, arguments)`.
  - Wait for completion via `client.get_workflow_handle(workflow_id).result()` (blocking).
  - Timeout per workflow type (e.g., triage run = 60 s, action workflow = 5 min) enforced by Temporal's `WorkflowOptions.start_to_close_timeout`.
  - Retry policy: Temporal's built-in retry mechanism (exponential backoff, max 3 attempts per activity, not per workflow).
- **Activity definitions (MEDIUM finding #5 address: activity timeout documentation):**
  - Each triage-graph node becomes a Temporal activity (e.g., `classify_intent`, `retrieve_knowledge`, `compose_response`).
  - Activities have explicit timeout configuration (in proto or code):
    - `schedule_to_close_timeout` = node's timeout (e.g., 30 s for classify, 10 s for guard).
    - `start_to_close_timeout` = per-activity hard deadline (e.g., 25 s for classify).
    - `heartbeat_timeout` = for long-running activities (retrieval with rerank might heartbeat every 5 s).
  - Activity timeout exceeded → Temporal retries per policy, then workflow fails with `ActivityTimeoutException`.
  - Documentation: every activity has a docstring specifying its timeout and what "timeout" means (schedule vs. start-to-close vs. heartbeat).
- **Deterministic state machine (§19.2 write-action state machine in S7):**
  - Workflow checkpoints state in Temporal (via `workflow.set_variable(state)`).
  - State transitions are idempotent: `execute_activity(classify_intent, input)` called twice with same input returns same result (Temporal's built-in deduplication).
  - Crash during activity execution: workflow resumes at the same checkpoint, activity is retried (or not, depending on retry policy).
- **Tenant context propagation:**
  - Workflow receives tenant_id in arguments.
  - All activities execute with tenant context set (via `set_context(tenant_id)`).
  - Context is NOT inferred from Workflow ID (explicit context passing, fail-closed if context is missing).
- **Error handling:**
  - Activity failure → caught by workflow, logged with full trace.
  - Workflow failure (all retries exhausted) → returned to the caller as a failed result (not an exception; exceptions are caught in the workflow, not propagated).
  - Temporal server failure (cluster down) → client.start_workflow() raises `ServiceUnavailableException`, caller retries at a higher level.

**Acceptance Criteria:**
1. ✓ `TemporalWorkflowEngine` class passes the **same workflow-engine contract suite** from MVP when running against Testcontainers Temporal cluster.
2. ✓ Workflow ID is deterministic; running the same input 3 times produces the same Workflow ID; only 1 workflow is actually executed (idempotency).
3. ✓ Triage graph nodes are wired as Temporal activities; workflow orchestrates them in the correct DAG order.
4. ✓ Workflow timeout (start_to_close) is enforced; if workflow runs > 60 s, it fails with `WorkflowTimeoutException`.
5. ✓ Activity timeout is enforced; if activity runs > its schedule_to_close_timeout, it times out and retries (up to 3 times).
6. ✓ Every activity has a docstring specifying its timeout (in comments at the top of the @activity function).
7. ✓ Tenant context is required; if not passed, workflow fails immediately with clear error message.
8. ✓ After Temporal cluster restart, workflow resumes from its last checkpoint; no duplicate side effects (idempotency property test).

---

### FR-CUTOVER-PLAN-01: Parity Checker & Feature Flag Orchestration
**Tier:** Tier A (unit tests) + Tier E (staging validation)  
**Definition of Done:**
- **Feature flags:**
  - `EVENT_BACKBONE_KAFKA` (boolean, default=false in MVP, will be true in S6): if true, use `KafkaEventBus` + Debezium; if false, use outbox poller.
  - `WORKFLOW_ENGINE_TEMPORAL` (boolean, default=false in MVP, will be true in S6): if true, use `TemporalWorkflowEngine`; if false, use in-process executor.
  - Flags are read from environment variables and cached at startup (immutable during runtime; restart required to change).
  - Flags are logged on startup (audit trail).
- **Dual-adapter mode in staging:** feature flags allow running both old (MVP) and new (S6) adapters in parallel to compare outputs.
  - When both flags are **off**: old adapters only (MVP behavior).
  - When both flags are **on**: new adapters only (S6 behavior).
  - When **mixed:** (e.g., Kafka on, Temporal off) for 1-week staging parallel run:
    - EventBus: publish to BOTH outbox (old) and Kafka (new); compare output at consumer.
    - WorkflowEngine: start workflow in BOTH in-process (old) and Temporal (new); compare results.
    - Comparison is logged but not blocking (both succeed independently).
- **Parity checker logic (MEDIUM finding #6 address: parity threshold tuning):**
  - After each event is processed by both pipelines, compare:
    - Event structure (envelope, payload, metadata) — must be byte-identical (after canonicalization).
    - Event ordering per tenant (partition) — must be identical offset-by-offset.
    - Processing latency (old vs. new) — track P50, P95, P99; alert if new is > 2× old (performance regression).
  - Comparison result is logged as:
    - ✓ Parity OK: events match.
    - ⚠ Parity warning: events differ in non-critical fields (e.g., timestamp diff > 1 s); log but do not alert.
    - ✗ Parity failure: events differ in critical fields (payload, type, tenant); alert immediately.
  - Threshold: 99.5% of events must be parity OK; if < 99.5%, cutover is blocked (admin must investigate).
- **Cutover process:**
  1. Deploy both adapters in staging with both flags off (MVP behavior).
  2. Turn on both flags simultaneously; verify parity for 1 week.
  3. If parity ≥ 99.5%, stage production deployment with both flags on.
  4. Monitor production for 24 h; if any parity failures, auto-rollback flags to off (in-process only).
  5. After 24 h clean, disable old adapters (outbox poller and in-process executor) in S6+1 cleanup phase.
- **Observability:**
  - Metric: `parity_checker.events_compared_total{adapter,status}` (counter, status = OK|warning|failure).
  - Metric: `parity_checker.events_latency_delta_ms{adapter}` (histogram: latency(new) - latency(old)).
  - Alert: if parity failure rate > 0.5% over 5-min window.
  - Dashboard: parity chart (% OK over time), latency comparison, event types with most mismatches.

**Acceptance Criteria:**
1. ✓ Feature flags are read from environment; logging on startup shows which adapters are active.
2. ✓ Both flags off → MVP adapters only (outbox poller, in-process executor).
3. ✓ Both flags on → S6 adapters only (Kafka, Temporal).
4. ✓ Mixed flags (e.g., Kafka on, Temporal off) → dual-adapter mode; events compared after processing both paths.
5. ✓ Parity checker compares event structure (envelope, payload); test generates 100 events and verifies comparison is logged for all 100.
6. ✓ Parity checker tracks latency difference; test publishes via both adapters, measures time, compares delta.
7. ✓ Parity threshold enforced: if 99.5% of events do NOT match, admin must explicitly override (flag in config) to proceed.
8. ✓ Cutover process documented: step-by-step procedure from staging to production (in runbook).
9. ✓ Auto-rollback: if parity failures spike in production, metric alert triggers and on-call can disable the new adapters via ops playbook.
10. ✓ Metrics and dashboard are live; Prometheus can scrape parity_checker metrics; Grafana dashboard shows parity trend and latency comparison.

---

## Non-Functional Requirements

### NFR-PROTO-01: Schema Evolution & Backward Compatibility
- All Protobuf files must maintain BACKWARD_TRANSITIVE compatibility (per buf policy).
- `buf breaking` CI check enforces this on every PR; failure blocks merge.
- Impact: old consumers can read new events; new consumers can read old events (with missing optional fields defaulting safely).

### NFR-EVENTBUS-01: Durability & Ordering
- **Durability:** all events persisted in Kafka with replication factor ≥ 2 (staging) / ≥ 3 (prod); retention ≥ 7 days.
- **Ordering:** per-tenant events must be processed in the exact order they were published (strict ordering guarantee).
  - Ensured by partition key = tenant_id and single-threaded consumer per partition.
- **At-least-once:** events are re-deliverable after consumer restart; idempotency deduplication prevents duplicates.

### NFR-EVENTBUS-02: Performance & Scalability (MEDIUM finding #4)
- **Throughput:** Kafka cluster must handle ≥ 1000 msgs/s (cumulative across all tenants) with P95 latency ≤ 100 ms (publish to broker).
- **Scalability:** should scale horizontally; adding more brokers increases throughput linearly.
- **Consumer lag:** must not exceed 5 min under steady-state load (20 msgs/s per tenant).
- **Disk usage:** 7-day retention at 1000 msgs/s ≈ 600 GB per topic (estimate; exact sizing in S6 spec).

### NFR-IDEMPOTENCY-01: Exactly-Once Semantics
- Consumers must guarantee exactly-once processing for side effects (e.g., Stripe API calls, policy decisions).
- Achieved via idempotency key + Redis/Postgres deduplication; verified by property tests.

### NFR-WORKFLOW-01: Determinism & Auditability
- Workflows must be deterministic: same input always produces same output (no random UUIDs, timestamps, or network calls that are not idempotent).
- Every workflow execution is audited: start, activity completion, state transition, finish are all logged.
- Logs are persisted in Temporal and searchable via `temporal workflow show <workflow_id>`.

### NFR-WORKFLOW-02: Timeout & Retry Policies (MEDIUM finding #5)
- Every activity has explicit timeout documentation in its docstring (schedule_to_close_timeout, start_to_close_timeout).
- Timeout values are tuned via profiling and load testing (not guesses); documented in S6.X spec.
- Retry policy is deterministic: exponential backoff with jitter, max retries specified per activity.

### NFR-CUTOVER-01: Zero Downtime Deployment
- Cutover from MVP to S6 happens behind feature flags with parity verification.
- No message loss during cutover; all in-flight messages complete or are replayed.
- Rollback is automated via feature flags (instant, no data migration needed).

### NFR-SECURITY-01: Tenant Isolation
- All Kafka messages and Temporal workflows include tenant context.
- Tenant A cannot read/write tenant B's events (enforced by partition key and workflow ID namespacing).
- Idempotency keys are tenant-scoped: `idempotency:{tenant_id}:{correlation_id}`.

---

## Acceptance Criteria

### Protobuf Contracts (FR-PROTO-01)
1. ✓ `packages/contracts/proto/` contains 6 `.proto` files; `buf build` passes without errors.
2. ✓ `buf breaking` passes when compared against baseline; no backward-incompatible changes.
3. ✓ Generated Python code imports from `py_contracts` module; `pyright --strict` passes.
4. ✓ Generated TypeScript compiles; `tsc --strict` passes.
5. ✓ Round-trip test: for all 6 message types, serialize → deserialize → equality check (18 pytest tests).
6. ✓ Proto comments include OpenAPI validation hints (required, pattern, etc.) for 100% of scalar fields.
7. ✓ No oneof fields; traceability arrays used instead for backward compatibility.
8. ✓ Integration test: Protobuf message is published via KafkaEventBus (S6 adapter), consumed, deserialized, and matches original.

### Kafka Adapter (FR-EVENTBUS-01)
9. ✓ `KafkaEventBus` passes all event-bus contract tests from S1.9 (at-least-once, ordering, dedup).
10. ✓ CloudEvents envelope is RFC 9222 compliant; schema validation passes.
11. ✓ Partition key is tenant_id; isolation property test passes (tenant A events never mix with tenant B).
12. ✓ Produces with acks="all"; broker outage causes EventPublishError within 30 s.
13. ✓ Published event round-trips through Kafka and deserializes correctly.
14. ✓ Metrics emitted on every publish (success and failure); Prometheus scrape contains all counters.
15. ✓ Tenant context mismatch raises ValueError before sending; test verifies no data leaves the client.

### Debezium Relay (FR-EVENTBUS-02)
16. ✓ Debezium connector deploys and runs in staging without errors.
17. ✓ First outbox INSERT propagates to Kafka within 5 s.
18. ✓ Transformed CDC event matches KafkaEventBus structure (CloudEvents envelope + Protobuf payload).
19. ✓ Schema Registry contains schemas for all event types; `buf breaking` blocks backward-incompatible uploads.
20. ✓ Cutover process (parallel run for 1 week): parity checker shows ≥ 99.5% parity between outbox poller and Debezium.
21. ✓ Snapshot handling: after Debezium startup, exactly 0 duplicate events from pre-cutover rows.
22. ✓ Replication slot lag monitored; alert fires if lag > 1 GB.

### Consumer Idempotency (FR-KAFKA-IDEMPOTENCY-01)
23. ✓ Redis fast path: SET correlation_id → idempotent; second write succeeds with no error.
24. ✓ Postgres fallback: unique constraint on (tenant_id, correlation_id); duplicate insert raises IntegrityError.
25. ✓ Redis unavailable → event still idempotent via Postgres (integration test).
26. ✓ Property test: 100 concurrent duplicate events → exactly 1 side effect (e.g., 1 Stripe refund call).
27. ✓ Idempotency key is stable across retries (derived from event id, not wall-clock time).
28. ✓ Postgres idempotent result column stores and deserializes JSON correctly.
29. ✓ TTL job runs weekly; rows older than 90 days are deleted.

### DLQ & Replay (FR-KAFKA-DLQ-01)
30. ✓ After 3 failed retries, event is published to DLQ (not dropped).
31. ✓ DLQ event retains original correlation_id, event_type, tenant_id and adds dlq_reason, dlq_retry_count, dlq_timestamp.
32. ✓ Replay CLI works: `triage-cli dlq replay --topic X --start Y --end Z --tenant T` lists events.
33. ✓ Replayed event is republished to original topic; consumer processes it; if already processed, skipped and logged as idempotent skip.
34. ✓ Replay is recorded in audit log with user, timestamp, event count.
35. ✓ Replay rate-limiting enforced: > 10/s triggers backpressure; test verifies via property test.
36. ✓ DLQ retention: events older than 30 days are deleted.
37. ✓ Metrics emitted on DLQ publish; Prometheus scrape shows counter.

### Priority Lanes (FR-PRIORITY-LANES-01)
38. ✓ Two consumer groups exist; both subscribed to triage.messages.{env}.
39. ✓ Events correctly routed: 10 chat + 10 email messages → all chat processed by chat lane, all email by email lane.
40. ✓ Chat latency SLO (P95 ≤ 2 s) met under 20 msgs/s for 2 min.
41. ✓ Email latency SLO (P95 ≤ 60 s) met under normal load.
42. ✓ Starvation test: 100 email + 5 chat → chat processed within 2 s despite email backlog.
43. ✓ Worker pool sizes configurable via environment; metrics report pool size.
44. ✓ Email backlog boost heuristic: 150 email messages → worker count increases from 5 to 8 for 15 min, then decreases.
45. ✓ Metrics emitted for both lanes; Prometheus scrape shows all four metrics.

### Temporal Adapter (FR-WORKFLOW-ENGINE-01)
46. ✓ `TemporalWorkflowEngine` passes workflow-engine contract suite from MVP.
47. ✓ Workflow ID is deterministic; same input → same Workflow ID; only 1 execution.
48. ✓ Triage graph nodes are Temporal activities; workflow orchestrates them in correct DAG order.
49. ✓ Workflow timeout (start_to_close) enforced; runs > 60 s fail with WorkflowTimeoutException.
50. ✓ Activity timeout enforced; runs > its schedule_to_close_timeout timeout out and retry (max 3).
51. ✓ Every activity has timeout documentation in docstring (schedule_to_close, start_to_close).
52. ✓ Tenant context required; missing context fails immediately with clear error.
53. ✓ After cluster restart, workflow resumes from checkpoint; no duplicate side effects.

### Parity Checker (FR-CUTOVER-PLAN-01)
54. ✓ Feature flags read from environment; logged on startup.
55. ✓ Both flags off → MVP adapters only.
56. ✓ Both flags on → S6 adapters only.
57. ✓ Mixed flags → dual-adapter mode; events compared after both paths process.
58. ✓ Parity checker compares event structure; test generates 100 events and verifies comparison logged for all.
59. ✓ Parity latency delta tracked; test publishes via both adapters and measures delta.
60. ✓ Parity threshold enforced: < 99.5% match → blocks cutover.
61. ✓ Cutover process documented in runbook.
62. ✓ Auto-rollback on parity failure spike (admin can disable new adapters via ops playbook).
63. ✓ Metrics and dashboard live; Prometheus scrapes parity metrics; Grafana shows trend.

---

## Out of Scope

- **Temporal UI and advanced observability:** Temporal UI deployment and custom Temporal metrics are deferred to S11 (production hardening).
- **Advanced Kafka tuning (e.g., exactly-once semantics via transactions, stream processing DSL):** MVP uses at-least-once with idempotency; exact-once via Kafka transactions is investigated in Stage 3 roadmap.
- **Multi-region Kafka replication (e.g., MirrorMaker):** Single-region staging and production clusters only; multi-region failover is a Stage 3 capability.
- **Rego/OPA policy validation in EventBus:** policies are applied at the triage decision stage (S7), not in the event backbone.
- **Encryption at rest in Kafka:** events are encrypted at application level (via DEK in envelope); Kafka-level encryption is infrastructure config (not code).
- **Kafk Exactly-Once Semantics (EOS) mode:** added risk and complexity; idempotency + DLQ is simpler and sufficient for MVP.
- **Temporal sandboxing for untrusted workflows:** all workflows are authored by Triage engineering; user-defined workflows (v2 roadmap) will introduce sandboxing.
- **Kafka Connect connectors beyond Debezium:** SMT transforms are limited to outbox relay; other integrations use direct SDK calls (S7+).
- **Consumer lag dashboards and auto-scaling based on lag:** basic lag monitoring only; auto-scaling is S9 (SLA engine).

---

## Design Review Findings & Responses

### Finding: HIGH #1 — Protobuf Snapshot Safety
**Issue:** Optional fields in proto3 can lead to ambiguous snapshots (distinguishing between "field not set" and "field set to default value"); older consumers might not handle newer optional fields correctly.

**Response - ADDRESSED in FR-PROTO-01:**
- Explicit `optional` keyword in all proto files (proto3 ≥ 1.12) makes presence unambiguous.
- Round-trip tests verify serialization captures presence correctly.
- Backward-compatibility tests ensure old consumers treat new optional fields as "not set" safely.
- buf breaking policy enforces no field removal (would break older consumers).

### Finding: HIGH #2 — Protobuf Field Validation
**Issue:** Proto messages lack explicit validation rules for required fields (e.g., tenant_id must not be empty, age must be ≥ 0).

**Response - ADDRESSED in FR-PROTO-01:**
- OpenAPI 3.1 validation hints embedded in proto comments (e.g., `// required`, `// minValue: 0`).
- Application-level validation in proto decoder (Pydantic validator in py_contracts).
- Custom validator for tenant_id in EventBus adapter: missing or empty tenant_id raises ValueError before publishing.
- Criteria #7 and #14 verify validation is in place.

### Finding: MEDIUM #1 — Idempotency Race Conditions
**Issue:** Concurrent retries of the same event might result in duplicate processing if idempotency key is not deterministic or if Redis and Postgres get out of sync.

**Response - ADDRESSED in FR-KAFKA-IDEMPOTENCY-01:**
- Idempotency key derived from event correlation_id (deterministic, not wall-clock time).
- Property test with Hypothesis simulating 100 concurrent retries; exactly-once execution verified.
- Redis and Postgres consistency: if mismatched, Postgres (source of truth) wins; logged as warning but no replay.
- Criteria #26 verifies property test passes.

### Finding: MEDIUM #2 — Snapshot Safety During Debezium Cutover
**Issue:** Pre-cutover outbox rows might be replayed by Debezium after it starts, causing duplicate event delivery.

**Response - ADDRESSED in FR-EVENTBUS-02:**
- Cutover process: drain outbox poller, mark all existing rows as processed, then enable Debezium (isolation).
- Debezium snapshot.mode = "never" in staging (no snapshot; only new inserts streamed).
- Criterion #21 verifies exactly 0 duplicate events from pre-cutover rows.

### Finding: MEDIUM #3 — Consumer Idempotency Key Stability
**Issue:** If idempotency key changes across retries (e.g., includes retry attempt number), duplicate events are treated as distinct, risking duplicate processing.

**Response - ADDRESSED in FR-KAFKA-IDEMPOTENCY-01:**
- Idempotency key MUST be stable (from correlation_id).
- Code review checklist includes: "Verify idempotency key is deterministic and does not include retry attempt or time."
- Criterion #27 verifies key stability across retries.

### Finding: MEDIUM #4 — Worker Pool Efficiency Under Load
**Issue:** Static thread pool sizes (20 chat, 5 email) might be inefficient under uneven load; queue depth might spike, causing latency degradation.

**Response - ADDRESSED in FR-PRIORITY-LANES-01:**
- Worker pool sizes are configurable via environment variables (not hardcoded).
- Queue depth monitoring with alerts (if > 50% capacity).
- Heuristic starvation prevention: boost email workers temporarily if backlog > 100 (tuned in Stage 2 based on real-world load).
- Temporal-based routing (S9) provides more sophisticated load-aware assignment.
- Criteria #43–45 verify heuristics work and metrics are available for tuning.

### Finding: MEDIUM #5 — Activity Timeout Documentation
**Issue:** Timeout values for triage-graph activities (classify, retrieve, compose, guard) are not explicitly documented; if a timeout is too short, activities repeatedly timeout and retry indefinitely.

**Response - ADDRESSED in FR-WORKFLOW-ENGINE-01:**
- Every Temporal activity has explicit timeout configuration (schedule_to_close, start_to_close, heartbeat).
- Timeout values are documented in activity docstring (e.g., "classify_intent: schedule_to_close_timeout = 30s, start_to_close_timeout = 25s").
- Timeout tuning is part of S6 profiling (load tests to identify bottleneck activities).
- Criteria #51 verifies docstrings are present.

### Finding: MEDIUM #6 — Parity Threshold Tuning
**Issue:** Parity threshold of 99.5% might be too strict or too loose depending on expected divergence between old and new adapters; no clear procedure for tuning.

**Response - ADDRESSED in FR-CUTOVER-PLAN-01:**
- Threshold is configurable via environment variable (not hardcoded).
- Cutover process includes 1-week staging parallel run to measure actual parity; threshold is tuned based on observed divergence.
- If parity < 99.5%, admin must explicitly override (flag in config); decision is audited.
- Runbook includes troubleshooting steps for investigating parity failures.
- Criterion #60 verifies threshold is enforced; criteria #61–62 verify human-in-the-loop override process.

---

## Implementation Notes & Assumptions

1. **Kafka setup:** KRaft-mode Kafka cluster (no Zookeeper) is available in staging; 3 brokers minimum. Broker configuration provided by DevOps (S6.2 spec).
2. **Temporal setup:** Temporal server is running in staging (docker-compose or managed service). Temporal DB (Postgres, MySQL, or Cassandra) is configured separately.
3. **Schema Registry:** Confluent Schema Registry is available and configured for Protobuf support. `packages/contracts` has a buf plugin to auto-generate Avro schemas from proto files (or manual hand-crafted schemas if needed).
4. **Feature flags:** implemented via environment variables (read at startup, immutable during runtime). No runtime flag evaluation needed for S6 (dynamic flags are a Stage 3 capability).
5. **Monitoring:** Prometheus and Grafana are available in staging. OpenTelemetry SDK is integrated into all services (already in MVP).
6. **Load testing:** k6 tests are written as part of S6 acceptance criteria; load profile is defined in S6.X spec.
7. **Rollback plan:** if parity failures occur in production, feature flags are set to false (disables new adapters immediately); no data migration or state cleanup required (stateless flag toggle).

---

## Success Metrics & Verification

| Metric | Target | Verification Method |
|---|---|---|
| Protobuf compilation | 100% (0 buf errors) | `buf build` in CI gate |
| Schema Registry parity | 100% (0 schema mismatches) | buf plugin + schema diff test |
| Kafka event publishing latency | P95 ≤ 100 ms | k6 benchmark test |
| Consumer idempotency | 100% exactly-once | Property test with 100 concurrent duplicates |
| Event ordering per tenant | 100% correct | Order test: publish N events, consume N, verify sequence |
| Parity score (old vs. new) | ≥ 99.5% | Parity checker in staging for 1 week |
| Chat latency SLO | P95 ≤ 2 s | k6 test at 20 msgs/s |
| Email latency SLO | P95 ≤ 60 s | k6 test at steady state |
| DLQ functionality | 100% (all failed events route to DLQ) | Integration test: 3 failures → DLQ |
| Replay functionality | 100% (replayed events processed exactly-once) | Replay test: DLQ → original topic → no duplicate side effect |
| Workflow determinism | 100% (same input → same output) | Property test: Temporal contract suite |
| Temporal timeout enforcement | 100% (exceeded timeouts cause failure) | Activity timeout test: run activity > timeout → times out |

---

## Definition of Done for Sprint 6

### Code
- [ ] All 6 proto files compile and pass `buf breaking` CI gate.
- [ ] KafkaEventBus adapter implements EventBus interface; passes contract suite.
- [ ] Debezium connector deploys and streams outbox changes to Kafka; parity ≥ 99.5% with outbox poller.
- [ ] Consumer idempotency (Redis + Postgres) implemented; property tests pass.
- [ ] DLQ topic and replay CLI tool deployed; tested.
- [ ] Chat and email consumer groups configured; priority lane logic working.
- [ ] TemporalWorkflowEngine adapter implements WorkflowEngine interface; passes contract suite.
- [ ] Feature flags implemented; dual-adapter mode works.
- [ ] Parity checker runs and logs comparison results.

### Tests
- [ ] Contract tests for EventBus pass against both outbox poller and Kafka adapter.
- [ ] Contract tests for WorkflowEngine pass against both in-process executor and Temporal adapter.
- [ ] Proto round-trip tests pass (18 test cases).
- [ ] Idempotency property test passes (100 concurrent duplicates → 1 side effect).
- [ ] Priority lane tests pass (chat SLO met, email SLO met, no starvation).
- [ ] Parity checker test passes (generates 100 events, compares via both adapters).
- [ ] DLQ + replay test passes (failed event routes to DLQ, replayed event is processed exactly-once).
- [ ] Timeout and retry tests pass (activity timeout, workflow timeout, exponential backoff).

### Documentation
- [ ] Activity docstrings document timeout values (schedule_to_close, start_to_close).
- [ ] Cutover process documented in runbook (step-by-step staging → production).
- [ ] Proto schema documented (events.proto, messages.proto, etc. comments explain each field).
- [ ] API changes to EventBus and WorkflowEngine documented (no breaking changes; both use same interface as MVP).
- [ ] Feature flag environment variables documented (EVENT_BACKBONE_KAFKA, WORKFLOW_ENGINE_TEMPORAL).

### Operational
- [ ] Metrics dashboard created: parity score, Kafka latency, consumer lag, worker pool depth, DLQ events.
- [ ] Alerts configured: parity failure, Kafka broker down, consumer lag > 5 min, DLQ events, Temporal workflow failures.
- [ ] Staging parity run completed for ≥ 1 week; ≥ 99.5% parity achieved.
- [ ] Rollback procedure tested: disable feature flags, verify old adapters take over, no data loss.
- [ ] Production cutover checklist signed off by tech lead and SRE.

### Design
- [ ] Design review findings (2 HIGH, 4 MEDIUM) addressed in code or deferred with justification.
- [ ] Backward-compatibility story locked: no breaking changes to EventBus or WorkflowEngine interfaces.
- [ ] Tenant isolation verified: no data leaked between tenants; partition keys correct.

---

## Traceability to Feature Request

| Feature Request Item | Requirement | Acceptance Criteria |
|---|---|---|
| 6 proto files | FR-PROTO-01 | #1–8 |
| Kafka + Debezium adapter | FR-EVENTBUS-01, FR-EVENTBUS-02 | #9–22 |
| Consumer idempotency (Redis + Postgres) | FR-KAFKA-IDEMPOTENCY-01 | #23–29 |
| DLQ + replay tool | FR-KAFKA-DLQ-01 | #30–37 |
| Priority lanes (chat vs. email) | FR-PRIORITY-LANES-01 | #38–45 |
| Temporal adapter for WorkflowEngine | FR-WORKFLOW-ENGINE-01 | #46–53 |
| Cutover plan + parity checker | FR-CUTOVER-PLAN-01 | #54–63 |

---

**Document Status:** Ready for implementation. No further clarification needed. Design review findings are addressed in requirements or deferred to later sprints with justification.

