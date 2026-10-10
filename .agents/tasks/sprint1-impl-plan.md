# Sprint 1 Implementation Plan
**AI-Powered Support Triage Agent — Message Ingestion & Conversation Core**

**Document Version:** 1.0  
**Date:** October 2026  
**Target Duration:** 2 weeks (10 business days)  
**Team Size:** 2–3 developers  

---

## Executive Summary

Sprint 1 builds the complete **message ingestion pipeline** end-to-end: normalize messages from all channels (email via Zendesk, web chat widget), enforce idempotency, coalesce bursts, resolve identities, encrypt PII, write events to the outbox, and trigger triage workers. All 10 deliverables are grounded in the existing Sprint 0 foundation (PostgreSQL with RLS, tenant context, structured logging, Alembic migrations).

**Out-of-the-box architecture:**
- **Ingestion**: Fast path (202 Accepted) → message persisted durably → background task queues for triage
- **Channels**: Email via Zendesk webhook (signed, with write-back), Web chat (Preact widget, SSE streaming)
- **Normalization**: Per-channel normalizers (email threading via Message-ID, web chat, Zendesk comment routing)
- **Idempotency**: Provider message IDs + deterministic body hashes → exactly-once semantics
- **Encryption**: Envelope encryption (DEK+KEK) before storage; Presidio PII redaction before processing
- **Identity**: Cross-channel customer deduplication (email/phone/external ID merge); IAL1 (channel-asserted)
- **Coalescing**: Redis debounce + conversation lock + heartbeat; cancels at node boundary
- **Outbox**: Transactional write of ingestion events → durable async processing without Kafka

**Success criteria:**
- All message paths reach the database encrypted, de-duplicated, and audit-logged
- J1 scenario (WISMO email → auto-resolve) flows end-to-end to the triage worker
- Tenant isolation enforced at every layer (RLS, composite keys, tenant_id in all contexts)
- Zero message loss (transactional outbox)
- < 200ms p99 ingestion latency (202 response time)

---

## Architecture Decisions Recorded

| Decision | Rationale |
|---|---|
| **202 Accepted response** | Message persisted durably in database before 202 returned; client gets immediate feedback; triage happens async via outbox poller. Matches HTTP semantics for fire-and-forget ingestion. |
| **Idempotency-Key header** | HTTP standard (RFC 7231). Deterministic key from provider_message_id + body_hash ensures N duplicate deliveries yield exactly 1 message row. Prevents duplicate triage runs on network retries. |
| **Per-channel normalizers** | Each channel has unique semantics (email threading via Message-ID, Zendesk comment routing, widget message IDs). Dedicated normalizer per channel preserves these; NormalizerFactory plugs in new channels without touching core. |
| **Envelope encryption (DEK+KEK)** | Separates data-at-rest encryption from PII handling. DEK (Data Encryption Key) is versioned and stored per tenant; KEK (Key Encryption Key) is managed by AWS KMS or local key file. Allows key rotation, audit of who decrypted what, and compliance separation. |
| **Presidio pseudonymization** | Detects PII entities in plaintext body, replaces with vault tokens before any LLM/downstream system sees it. Vault stores the mapping. On delivery (chat widget, Zendesk write-back), secrets are re-hydrated. Reduces breach surface. |
| **Transactional outbox** | Every message insert triggers an outbox event in the same transaction. Outbox poller picks up events and delivers them to downstream (triage worker queue, webhooks, Kafka later). Guarantees: no message loss, ordering per conversation, at-least-once delivery. |
| **Redis conversation lock + debounce** | Prevents race conditions when multiple messages arrive for the same conversation simultaneously (e.g., chat burst, email thread). Lock prevents concurrent triage runs. Debounce (4s chat, 0s email) batches rapid messages. At node boundary, coalescing window cancels and restarts work. |
| **Composite keys (tenant_id, id)** | Every table has (tenant_id, id) as primary key. All foreign keys reference both columns. Postgres RLS policies check tenant_id on every query. One misconfigured query can never leak across tenants. |
| **SSE for real-time chat** | Server-Sent Events: simple, HTTP/1.1 compatible, no CORS complexity, no persistent connection overhead on the backend. Client opens GET /v1/streams/conversations/{id} and gets a text/event-stream with messages and triage status updates. |
| **Preact widget (Shadow DOM)** | Preact: ~3KB core, no JSX required (plain TS functions). Shadow DOM: isolates CSS, prevents parent app conflicts. Bundle < 40KB gzipped. AI disclosure built-in: "Powered by AI • Human review available." |

---

## Monorepo & Package Layout

**After Sprint 1, the layout is:**

```
d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-\
├── packages/
│   └── py_core/                          # ✅ Exists (Sprint 0)
│       ├── py_core/
│       │   ├── db.py                     # Tenant context, session factory
│       │   ├── tenant.py                 # @require_tenant decorator
│       │   ├── errors.py                 # RFC 9457 errors
│       │   ├── logging.py                # Structured, PII-free logging
│       │   ├── audit.py                  # Audit logging + hash chain
│       │   ├── otel.py                   # OpenTelemetry setup
│       │   └── testing/                  # Test fixtures
│       │       ├── fixtures.py
│       │       ├── factories.py
│       │       └── fakes.py              # FakeLLM, FakeClock, etc.
│       ├── alembic/
│       │   ├── versions/
│       │   │   ├── 0001_baseline_mvp_schema.py        # ✅ Exists
│       │   │   ├── 0002_audit_hash_chain_trigger.py   # ✅ Exists
│       │   │   ├── 0003_rls_policies_sprint1.py       # 🆕 S1.1–S1.9
│       │   │   └── alembic.ini
│       │   └── env.py
│       └── pyproject.toml
│
├── services/
│   ├── api/                              # 🆕 FastAPI ingestion + streaming
│   │   ├── src/triage/
│   │   │   ├── api/
│   │   │   │   ├── main.py               # FastAPI app, middleware, error handling
│   │   │   │   ├── __init__.py
│   │   │   │   └── endpoints/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── messages.py       # S1.2: POST /v1/conversations/{id}/messages (202)
│   │   │   │       ├── streams.py        # S1.2: GET /v1/streams/conversations/{id} (SSE)
│   │   │   │       ├── webhooks.py       # S1.3: POST /v1/webhooks/zendesk (signature verified)
│   │   │   │       └── conversations.py  # S1.9: GET /v1/conversations/{id}, status tracking
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── message.py            # S1.1: CanonicalMessage, ChannelType, SenderType, etc.
│   │   │   │   ├── conversation.py       # S1.9: ConversationStatus, ConversationModel, queries
│   │   │   │   └── events.py             # S1.7: OutboxEvent schema
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── normalizers.py        # S1.1: EmailNormalizer, WebChatNormalizer, ZendeskNormalizer, NormalizerFactory
│   │   │   │   ├── idempotency.py        # S1.1: IdempotencyManager, body hash, provider ID matching
│   │   │   │   ├── encryption.py         # S1.6: EnvelopeEncryption (DEK/KEK), round-trip encrypt/decrypt
│   │   │   │   ├── pii_handler.py        # S1.6: Presidio integration, pseudonymization, vault token storage
│   │   │   │   ├── identity.py           # S1.5: IdentityResolver, email/phone/external ID merge, IAL1 assignment
│   │   │   │   ├── coalescing.py         # S1.4: MessageCoalescer, Redis debounce, conversation lock, TTL
│   │   │   │   ├── outbox.py             # S1.7: OutboxWriter, transactional event durability
│   │   │   │   └── zendesk_webhook.py    # S1.3: Signature verification, event routing, write-back
│   │   │   └── __init__.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── conftest.py               # Pytest fixtures, Testcontainers setup
│   │   │   ├── test_normalizers.py       # S1.1 unit tests: email threading, idempotency keys, all channels
│   │   │   ├── test_idempotency.py       # S1.1 unit tests: exactly-once semantics, property tests
│   │   │   ├── test_encryption.py        # S1.6 unit tests: round-trip, different tenant DEKs fail
│   │   │   ├── test_pii_handler.py       # S1.6 unit tests + evals: Presidio integration, vault
│   │   │   ├── test_identity.py          # S1.5 unit tests: merge rules, no cross-tenant merges, IAL1
│   │   │   ├── test_coalescing.py        # S1.4 unit tests: FakeClock tests, debounce timing, lock recovery
│   │   │   ├── test_messages_endpoint.py # S1.2 integration tests: 202 Accepted, 409 conflict, stream URL
│   │   │   ├── test_webhooks.py          # S1.3 integration tests: signature verification, event routing
│   │   │   ├── test_outbox.py            # S1.7 integration tests: at-least-once, ordering, consumer dedupe
│   │   │   └── acceptance/
│   │   │       ├── test_j1_wismo.py      # S1.10: J1 scenario (email WISMO → auto-resolved)
│   │   │       ├── test_j2_coalescing.py # S1.10: J2 scenario (chat burst coalesces into 1 triage run)
│   │   │       └── test_j3_zendesk_sync.py # S1.10: J3 scenario (ticket comment → triage → write-back)
│   │   ├── pyproject.toml
│   │   └── requirements.txt
│   │
│   ├── triage_worker/                    # 🆕 Background task consumer
│   │   ├── src/triage_worker/
│   │   │   ├── main.py                   # Worker entry point, outbox poller loop
│   │   │   ├── consumer.py               # Consume OutboxEvent, queue triage run (prep for S2)
│   │   │   └── __init__.py
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   └── test_consumer.py          # Integration: outbox → worker queue
│   │   └── pyproject.toml
│   │
│   └── knowledge_worker/                 # Placeholder for S3+
│       ├── src/knowledge_worker/
│       │   ├── main.py
│       │   └── __init__.py
│       ├── pyproject.toml
│       └── README.md
│
├── packages/
│   └── widget/                           # 🆕 Preact chat widget (S1.8)
│       ├── src/
│       │   ├── widget.ts                 # Preact component, SSE client, AI disclosure
│       │   ├── styles.css                # Scoped (Shadow DOM), WCAG AA contrast
│       │   ├── build.config.ts           # esbuild config, < 40KB gzip target
│       │   └── __init__.ts
│       ├── tests/
│       │   ├── test_widget.playwright.ts # Smoke tests: rendering, keyboard nav, CSAT
│       │   └── test_accessibility.ts     # axe-core scan
│       ├── package.json                  # uv managed
│       └── tsconfig.json
│
├── ml/
│   ├── evals/                            # 🆕 Evaluation datasets (S2–S3, seeded in S1)
│   │   ├── golden/
│   │   │   ├── intents_v0.jsonl          # 300 rows (S1 bootstrap), grows to 3K by GA
│   │   │   └── conversations_v0.jsonl    # 20 scenarios, S1.10 acceptance gate
│   │   ├── redteam/
│   │   │   └── injection_v0.jsonl        # 100 OWASP LLM Top 10 patterns
│   │   ├── conftest.py
│   │   └── eval_harness.py               # Metric computation (top-1 acc, macro-F1, etc.)
│   │
│   └── prompts/                          # 🆕 Versioned prompt templates
│       ├── compose_v1.md                 # Composition prompt (S3+, stubbed in S1)
│       ├── classify_v1.md                # Classification prompt (S2, stubbed in S1)
│       └── version.txt                   # Current version index
│
├── Docs/
│   ├── implementation-plan.md             # ✅ Exists (overarching 3-stage plan)
│   ├── architecture.md                    # 📋 TBD: runtime architecture, data flow diagrams
│   └── api.md                             # 📋 TBD: OpenAPI spec (auto-generated from FastAPI)
│
├── .agents/
│   └── tasks/
│       └── sprint1-impl-plan.md          # 📍 This file
│
└── [root files]
    ├── pyproject.toml                    # ✅ Exists: workspace definition
    ├── Makefile                          # ✅ Exists: make up, make test, make lint
    ├── docker-compose.yml                # ✅ Exists (Sprint 0): Postgres, Redis, MinIO, Mailpit, Langfuse
    ├── .github/workflows/
    │   ├── lint.yml                      # ✅ Exists: ruff, mypy, trivy
    │   ├── test.yml                      # ✅ Exists: pytest, coverage gates
    │   └── integration.yml               # ✅ Exists: Testcontainers, RLS audit
    └── tools/
        └── docker-compose.yml            # ✅ Exists: local dev stack
```

---

## Dependencies to Add

**py_core/pyproject.toml** (add to existing `dependencies`):
```toml
cryptography>=41.0        # AES-256-GCM for envelope encryption
presidio-analyzer>=2.2    # PII detection
presidio-anonymizer>=2.2  # PII pseudonymization
redis>=5.0                # Debounce, locks, distributed state
python-dotenv>=1.0        # .env config (dev)
httpx>=0.24               # Async HTTP client (webhooks, tool calls)
jsonschema>=4.20          # JSON schema validation
```

**services/api/pyproject.toml** (new file):
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "triage-api"
version = "0.1.0"
description = "Triage API — message ingestion and streaming"
requires-python = ">=3.12,<4"
dependencies = [
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "sqlalchemy[asyncio]>=2.0",
    "pydantic>=2.0",
    "py-core @ file://../../packages/py_core",
    "cryptography>=41.0",
    "presidio-analyzer>=2.2",
    "redis>=5.0",
    "httpx>=0.24",
    "python-multipart>=0.0.6",
]

[tool.pytest.ini_options]
# Same as py_core
```

**services/triage_worker/pyproject.toml** (new file):
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "triage-worker"
version = "0.1.0"
description = "Triage background worker — message processing"
requires-python = ">=3.12,<4"
dependencies = [
    "sqlalchemy[asyncio]>=2.0",
    "py-core @ file://../../packages/py_core",
    "redis>=5.0",
]
```

**packages/widget/package.json** (new file):
```json
{
  "name": "triage-widget",
  "version": "0.1.0",
  "type": "module",
  "dependencies": {
    "preact": "^10.18",
    "preact/signals": "^1.2"
  },
  "devDependencies": {
    "esbuild": "^0.19",
    "typescript": "^5.3",
    "@types/node": "^20.9",
    "playwright": "^1.39",
    "@axe-core/playwright": "^1.2"
  },
  "scripts": {
    "build": "esbuild src/widget.ts --bundle --minify --outfile=dist/widget.min.js",
    "test": "playwright test",
    "a11y": "playwright test test_accessibility.ts"
  }
}
```

---

## Implementation Plan (Ordered by Dependency)

### Phase 0: Database & Testing Foundation (Day 0–0.5)

- [ ] **0.1 Create RLS policies for Sprint 1 tables** (S0 foundation, but verify in context of S1 tables)
  - **What:** Alembic migration 0003 creates row-level security policies for `messages`, `conversations`, `triage_runs`, `predictions`, `entities`, `response_drafts`, `handoff_packets`, `kb_chunks`, `action_definitions`, `action_executions`. Policies enforce tenant isolation via `SET LOCAL app.tenant_id`. Unset context → zero rows. Admin role bypasses RLS for audits.
  - **Files:** `packages/py_core/alembic/versions/0003_rls_policies_sprint1.py`
  - **Verify:** Run `python -m pytest packages/py_core/tests/test_rls.py -v` (tests in py_core verify that SELECT/INSERT/UPDATE/DELETE all fail for cross-tenant). Expected: all tests pass, `pytest --cov` shows 100% coverage of RLS trigger functions.

- [ ] **0.2 Extend py_core testing fixtures with Testcontainers + Fakes**
  - **What:** Add `conftest.py` to `packages/py_core/py_core/testing/` with fixtures: `postgres_session()` (Testcontainers Postgres), `redis_client()` (Testcontainers Redis), `FakeLLM`, `FakeClock`, `FakeShopify`, `FakeStripe`, `InMemoryEventBus`. Each fake implements the same interface as the real adapter and is tested by the contract suite.
  - **Files:** `packages/py_core/py_core/testing/conftest.py`, `packages/py_core/py_core/testing/fakes.py`
  - **Verify:** Run `pytest packages/py_core/tests/ -v --tb=short`. Expected: fixtures load; no import errors.

### Phase 1: Message Normalization & Idempotency (Day 1–2)

- [ ] **1.1 Implement CanonicalMessage model and channel normalizers** (S1.1)
  - **What:** Create `packages/api/src/triage/models/message.py` with Pydantic models: `CanonicalMessage` (unified model for all channels), `MessageRequest` (API input), `MessageResponse` (API output), enums: `ChannelType`, `SenderType`, `MessageStatus`. Create `packages/api/src/triage/ingestion/normalizers.py` with normalizers: `EmailNormalizer` (email threading via Message-ID, In-Reply-To, References), `WebChatNormalizer` (widget messages), `ZendeskNormalizer` (comment routing). `NormalizerFactory` routes by channel type. All normalizers produce identical `CanonicalMessage` output.
  - **Files:** `packages/api/src/triage/models/message.py`, `packages/api/src/triage/ingestion/normalizers.py`
  - **Verify:** Run `pytest services/api/tests/test_normalizers.py -v`. Expected: ≥ 90% coverage. Test cases: email with threading (3 messages, verify parent_message_id chain), web chat (verify channel_id, sender_id), Zendesk comment (verify provider_message_id from comment.id). All assertions pass.

- [ ] **1.2 Implement IdempotencyManager (body hashing, deterministic keys, dedup checks)** (S1.1)
  - **What:** Create `packages/api/src/triage/ingestion/idempotency.py` with `IdempotencyManager` class. Methods: `compute_body_hash()` (SHA256 of normalized body), `generate_key()` (deterministic from tenant_id + provider_message_id or sender_id + body_hash), `check_idempotency()` (query database, return (is_duplicate, existing_msg_id)). Property test: N identical messages (same provider_id + body) yield exactly 1 row in database, others get 409 Conflict.
  - **Files:** `packages/api/src/triage/ingestion/idempotency.py`
  - **Verify:** Run `pytest services/api/tests/test_idempotency.py -v`. Expected: all property tests pass (Hypothesis generates 10–50 duplicate messages, verifies exactly-once). Deterministic key test passes (same inputs → same key). Database query test passes (409 on 2nd insert).

### Phase 2: Encryption & PII Handling (Day 2–3)

- [ ] **2.1 Implement envelope encryption (DEK/KEK, AES-256-GCM, key versioning)** (S1.6)
  - **What:** Create `packages/api/src/triage/ingestion/encryption.py` with `EnvelopeEncryption` class. Initialize with a KMS adapter (local key file in dev, AWS KMS in prod). Methods: `encrypt_message_body()` (plaintext → ciphertext + IV + dek_version), `decrypt_message_body()` (ciphertext + IV + dek_version → plaintext). Round-trip test: encrypt plaintext, decrypt, verify equals plaintext. Cross-tenant test: tenant A encrypts message, tenant B DEK cannot decrypt (cryptographic failure, logged). Key rotation test: add new DEK version, new messages use it, old messages still decrypt.
  - **Files:** `packages/api/src/triage/ingestion/encryption.py`
  - **Verify:** Run `pytest services/api/tests/test_encryption.py -v`. Expected: ≥ 90% coverage. Round-trip test passes. Cross-tenant decrypt raises `DecryptionError`. Key rotation test passes (old messages decrypt, new messages use new version).

- [ ] **2.2 Implement Presidio PII detection + pseudonymization vault** (S1.6)
  - **What:** Create `packages/api/src/triage/ingestion/pii_handler.py` with `PiiHandler` class. Uses Presidio Analyzer to detect entities (PERSON, PHONE_NUMBER, EMAIL_ADDRESS, CREDIT_CARD, IBAN, ORDER_ID custom pattern). For each detected entity: store raw value in `vault.pii_tokens` table (hash → token mapping), replace body with token (e.g., `[PII_PERSON_d1a2...]`). `re_hydrate()` method restores tokens from vault on delivery. Unit test: common PII patterns recognized. Eval test on `golden/guards`: Presidio recall ≥ 0.95 (detects PII before it reaches LLM).
  - **Files:** `packages/api/src/triage/ingestion/pii_handler.py`
  - **Verify:** Run `pytest services/api/tests/test_pii_handler.py -v`. Expected: ≥ 85% coverage. Unit tests pass (phone numbers, credit cards, custom patterns detected). Eval test: run Presidio on 200 PII-annotated sentences, check recall ≥ 0.95. No PII ever logged (grep for PERSON, PHONE_NUMBER in logs → no matches).

### Phase 3: Identity Resolution & Deduplication (Day 3)

- [ ] **3.1 Implement IdentityResolver (email/phone/external ID merge, IAL1 assignment)** (S1.5)
  - **What:** Create `packages/api/src/triage/ingestion/identity.py` with `IdentityResolver` class. Methods: `resolve_customer()` (given email/phone/external_id from message, find or create customer record), `merge_identities()` (mark email_alias / phone_alias on customer record if multiple channels), `assign_ial()` (assign IAL1 = "channel_asserted", stored as `customer.ial` enum). Merge test: 3 messages (email alice@example.com, chat alice@example.com, SMS +1–555–1234) → 1 customer record with email_alias and phone_alias. Cross-tenant test: tenant A's alice@example.com does NOT merge with tenant B's alice@example.com (separate customer records).
  - **Files:** `packages/api/src/triage/ingestion/identity.py`
  - **Verify:** Run `pytest services/api/tests/test_identity.py -v`. Expected: ≥ 90% coverage. Merge test passes (1 customer, 2 aliases). Cross-tenant isolation test passes (2 separate customers). IAL1 test passes (all ingested customers get IAL1).

### Phase 4: Coalescing & Locking (Day 3–4)

- [ ] **4.1 Implement MessageCoalescer (Redis lock, debounce, heartbeat, cancel-at-node-boundary)** (S1.4)
  - **What:** Create `packages/api/src/triage/ingestion/coalescing.py` with `MessageCoalescer` class. Uses Redis to store: conversation lock (LOCK_{tenant_id}_{conversation_id}), debounce timer (DEBOUNCE_{tenant_id}_{conversation_id}). Debounce intervals: 4s for chat, 0s for email, 2s for SMS. Acquire lock on first message → start debounce timer → collect messages for N seconds → release lock → trigger triage run. If lock already held: queue message, wait for release → merge into active batch. Heartbeat: every 10s, refresh lock TTL (30s). Cancel at node boundary: if 2+ messages queued and 12s elapsed, cancel and restart. `FakeClock` unit test: inject time advancement, verify debounce fires at correct intervals, lock releases, batch formed correctly. Deadlock test: simultaneous lock attempts on same conversation → one wins, others wait.
  - **Files:** `packages/api/src/triage/ingestion/coalescing.py`
  - **Verify:** Run `pytest services/api/tests/test_coalescing.py -v`. Expected: ≥ 85% coverage. Debounce timing tests pass (4s for chat, 0s for email). Lock contention test passes (one coalescer acquires, others queue). Cancel-at-boundary test passes (12s elapsed + 2+ messages → restart, old batch discarded). Deadlock test passes (30s TTL + heartbeat prevents hangs).

### Phase 5: Outbox Writer & Event Durability (Day 4)

- [ ] **5.1 Implement OutboxWriter (transactional event persistence)** (S1.7)
  - **What:** Create `packages/api/src/triage/ingestion/outbox.py` with `OutboxWriter` class and `OutboxPoller`. `OutboxWriter.write_event()`: insert row into `outbox` table (tenant_id, aggregate_type, aggregate_id, event_type, payload JSON, created_at) in same transaction as message insert. `OutboxPoller`: background task that polls `outbox` table via `SELECT ... FOR UPDATE SKIP LOCKED`, deserializes events, calls consumer handlers (e.g., `queue_for_triage`), marks row as processed. Guarantees: no message loss (durable insert), at-least-once delivery (idempotent consumer must dedupe), per-conversation ordering (consumer processes events sequentially per conversation_id). Contract test: outbox event schema matches expected shape; consumer adapter contract verifies downstream receives events correctly.
  - **Files:** `packages/api/src/triage/ingestion/outbox.py`, `packages/api/src/triage/models/events.py`
  - **Verify:** Run `pytest services/api/tests/test_outbox.py -v`. Expected: ≥ 80% coverage. Transactional insert test passes (message + outbox event both commit or both rollback). Poller test passes (events consumed, marked processed). Ordering test passes (events per conversation delivered in order). At-least-once test passes (consumer called ≥ 1 time; deduping consumer prevents side effects).

### Phase 6: Zendesk Webhook Receiver (Day 4–5)

- [ ] **6.1 Implement Zendesk webhook receiver (HMAC signature verification, event routing, write-back)** (S1.3)
  - **What:** Create `packages/api/src/triage/ingestion/zendesk_webhook.py` with `ZendeskWebhookHandler`. `POST /v1/webhooks/zendesk` receives signed JSON payload. Verify HMAC-SHA256 signature (header vs. computed from body + tenant secret). Route event types: `ticket.created` → capture ticket context, queue triage. `comment.created` → extract comment, normalize to CanonicalMessage, ingest. Raw webhook payload stored in S3 (audit trail). Write-back: after triage run completes, `write_to_zendesk()` posts result as internal note to ticket sidebar. Signature test: valid signature passes; invalid → 401. Event routing test: comment.created event parsed, normalized message inserted to database. S3 archive test: payload stored, retrievable (audit).
  - **Files:** `packages/api/src/triage/ingestion/zendesk_webhook.py`
  - **Verify:** Run `pytest services/api/tests/test_webhooks.py -v`. Expected: ≥ 85% coverage. Signature verification test passes (HMAC correct → 200, incorrect → 401). Event routing test passes (comment.created → message row created). S3 archive test passes (payload stored, retrievable). Duplicate webhook test passes (idempotency key prevents duplicate processing).

### Phase 7: Message Ingestion Endpoint & Streaming (Day 5–6)

- [ ] **7.1 Implement POST /v1/conversations/{id}/messages endpoint (202 Accepted, idempotency, background queueing)** (S1.2)
  - **What:** Create `packages/api/src/triage/api/endpoints/messages.py` with FastAPI router. `POST /v1/conversations/{id}/messages` accepts `MessageRequest` (body, sender_id, channel_id, etc.). Verify conversation exists (404 if not). Normalize via `NormalizerFactory`. Check idempotency → 409 if duplicate. Encrypt message body + pseudonymize PII. Insert into `messages` table + `outbox` table in transaction. Coalesce via `MessageCoalescer` (queue message, don't block). Return 202 with `stream_url` pointing to `GET /v1/streams/conversations/{id}`. Response time < 200ms p99. Failure handling: network error → 5xx retry. Duplicate → 409 with `X-Idempotency-Key` header.
  - **Files:** `packages/api/src/triage/api/endpoints/messages.py`
  - **Verify:** Run `pytest services/api/tests/test_messages_endpoint.py -v`. Expected: ≥ 90% coverage. 202 response test passes. Idempotency 409 test passes. Stream URL test passes (URL format correct, responds to GET). Latency test passes (p99 < 200ms on 100 concurrent requests). Failure recovery test passes (partial failures are retried).

- [ ] **7.2 Implement GET /v1/streams/conversations/{id} endpoint (SSE streaming, real-time updates)** (S1.2)
  - **What:** Create streaming endpoint in `messages.py`. Open connection, stream events: initial messages list (existing messages on conversation), then new messages + triage status updates (when available). Use Server-Sent Events (text/event-stream, `data: {...}\n\n` format). Client JavaScript opens connection, listens for events, updates UI in real-time. Termination: client closes, server closes gracefully. Heartbeat: every 30s, send `:heartbeat\n` comment to keep connection alive (proxy-friendly). Error handling: network error on stream → client reconnects to same endpoint.
  - **Files:** `packages/api/src/triage/api/endpoints/messages.py` (extended)
  - **Verify:** Run `pytest services/api/tests/test_messages_endpoint.py::test_sse_streaming -v`. Expected: stream opens, initial messages sent, heartbeat every 30s, connection closes cleanly. Bundle test: verify widget JavaScript connects to stream, receives events, updates DOM.

### Phase 8: Chat Widget v0 (Day 6–7)

- [ ] **8.1 Implement Preact chat widget (Shadow DOM, SSE client, AI disclosure, accessibility)** (S1.8)
  - **What:** Create `packages/widget/src/widget.ts` (Preact functional component + TypeScript). Widget creates Shadow DOM root. UI: message list (scrollable), message input (textarea), send button. On load: connect to `GET /v1/streams/conversations/{id}` SSE stream. Receive message events, append to list, scroll to bottom. On send: POST message to `/v1/conversations/{id}/messages`, get 202 + stream_url, update stream target. AI disclosure: header text "Powered by AI • Human review available" in gray. Accessibility: `aria-live="polite"` on message list, `aria-label` on buttons, keyboard nav (Tab for focus, Enter to send, Escape to close), WCAG AA color contrast (✓ tested with axe-core). Bundle: esbuild, Preact 10, no external CSS framework. Target size < 40KB gzipped. CSS: inline (Shadow DOM isolated), responsive (mobile + desktop). CSAT prompt: after message response, "Was this helpful?" Yes/No (optional, records feedback).
  - **Files:** `packages/widget/src/widget.ts`, `packages/widget/src/styles.css`, `packages/widget/build.config.ts`
  - **Verify:** Run `npm run build` (esbuild outputs dist/widget.min.js). File size check: `ls -lh dist/widget.min.js` → < 40KB. Bundle test: load HTML, import widget, verify renders in Shadow DOM, no console errors. Accessibility test: `npm run a11y` (Playwright + axe-core) → no violations. SSE connection test: mock SSE stream, send events, verify widget updates DOM. Keyboard nav test: Tab focuses input, Enter sends message, Escape closes.

### Phase 9: Conversation Model & Status Tracking (Day 7)

- [ ] **9.1 Implement Conversation schema, ORM model, and query helpers** (S1.9)
  - **What:** Create `packages/api/src/triage/models/conversation.py` with SQLAlchemy ORM model `Conversation`: fields for tenant_id, id, customer_id, channel_id, status (enum: open, pending, resolved, escalated), priority, subject, message_count (denormalized), unread_count, intent_primary, intent_secondary, confidence_score, is_auto_resolved, created_at, last_message_at, resolved_at. Indexes on (tenant_id, status), (tenant_id, created_at), (tenant_id, customer_id). Query helpers: `get_open_conversations(tenant_id)`, `get_at_risk(tenant_id)`, `get_assigned_to_agent(tenant_id, agent_id)`, `increment_message_count()`. RLS policies enforce tenant_id. `GET /v1/conversations/{id}` endpoint returns conversation + recent messages + triage run summary. `GET /v1/conversations` (list, paginated) returns conversations for tenant with status filter.
  - **Files:** `packages/api/src/triage/models/conversation.py`, `packages/api/src/triage/api/endpoints/conversations.py` (new)
  - **Verify:** Run `pytest services/api/tests/test_conversation_model.py -v`. Expected: ≥ 90% coverage. ORM tests pass (create, read, update). Query helper tests pass (list by status, order by created_at). RLS test passes (tenant A cannot see tenant B conversations). Denormalization test passes (message_count increments on new message).

- [ ] **9.2 Implement Alembic migration for Conversation table** (S1.9)
  - **What:** Create `packages/py_core/alembic/versions/0004_conversation_table_sprint1.py` migration. Creates `conversations` table with composite key (tenant_id, id), foreign keys to (tenants, customers, channels), indexes, RLS policy. Adds `UPDATE conversations` trigger to set `updated_at` on every write. RLS policy: `SELECT/INSERT/UPDATE/DELETE` only if `tenant_id = current_setting('app.tenant_id')`.
  - **Files:** `packages/py_core/alembic/versions/0004_conversation_table_sprint1.py`
  - **Verify:** Run `alembic upgrade head` (applies all migrations). Then run RLS test: set tenant_id context, query conversations → only tenant's rows returned. Unset context → zero rows. Audit log test: every INSERT/UPDATE to conversations is logged.

### Phase 10: FastAPI App Skeleton & Middleware (Day 7–8)

- [ ] **10.1 Create FastAPI app with middleware, tenant context injection, error handling** (S1.2, S1.3)
  - **What:** Create `packages/api/src/triage/api/main.py` (FastAPI app factory). Register middleware: `TenantMiddleware` (extract tenant_id from request header `X-Tenant-ID`, set in context via `contextvars`), `LoggingMiddleware` (structure logs, redact PII), `ErrorHandlerMiddleware` (catch exceptions, return RFC 9457 errors). Register routers: `messages.router`, `webhooks.router`, `conversations.router`. Add dependencies: `get_tenant()` → yields tenant_id from context, raises 400 if missing. Health check: `GET /v1/health` → 200 OK (verify DB connection). Readiness: `GET /v1/ready` → 200 if DB + Redis + Zendesk API reachable, 503 if any dependency down.
  - **Files:** `packages/api/src/triage/api/main.py`, `packages/api/src/triage/api/middleware.py`
  - **Verify:** Run `python -m pytest services/api/tests/test_api_main.py -v`. Expected: app loads, middleware stack intact, tenant context injected, error handler converts exceptions to RFC 9457 responses. Health check test passes (200 on healthy, 503 on component down).

- [ ] **10.2 Create triage_worker consumer (outbox poller + background task queue)** (S1.7, S1.10 prep)
  - **What:** Create `services/triage_worker/src/triage_worker/main.py` (entry point). Outbox poller loop: every 1s, query `SELECT * FROM outbox WHERE processed_at IS NULL ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED`. For each event: deserialize payload, call handler (e.g., `handle_message_ingested`), mark `processed_at = now()`. Handlers: `handle_message_ingested` → log message received (prep for S2 triage graph). Graceful shutdown: on SIGTERM, finish in-flight events before exit. Error handling: if event handler fails, retry with exponential backoff (1s, 2s, 4s, max 5 attempts); after max retries, move to dead-letter queue. Monitoring: log event processing latency (p50, p95, p99), handler errors per event_type.
  - **Files:** `services/triage_worker/src/triage_worker/main.py`, `services/triage_worker/src/triage_worker/consumer.py`
  - **Verify:** Run `pytest services/triage_worker/tests/test_consumer.py -v`. Expected: ≥ 80% coverage. Poller test passes (events processed in order, marked processed). Retry test passes (failed handler retried, success on 2nd attempt). Dead-letter test passes (after max retries, event moved to DLQ). Graceful shutdown test passes (in-flight events finished, new events not started).

### Phase 11: Integration Tests & Contract Suites (Day 8–9)

- [ ] **11.1 Implement contract tests for all ports (EventBus, integrations, API)** (Support all phases)
  - **What:** Contract test suites verify adapters (real and fakes) implement the same interface. Create `services/api/tests/contracts/`:
    - `test_event_bus_contract.py`: real Outbox adapter + fake InMemoryEventBus run same tests (publish event, subscribe, ordering, deduping)
    - `test_zendesk_contract.py`: recorded VCR cassettes for Zendesk webhook events, FakeZendesk returns same responses
    - `test_kms_contract.py`: LocalKMS (dev file) + AWS KMS (prod) both encrypt/decrypt identically
  - **Files:** `services/api/tests/contracts/test_event_bus_contract.py`, `services/api/tests/contracts/test_zendesk_contract.py`, `services/api/tests/contracts/test_kms_contract.py`
  - **Verify:** Run `pytest services/api/tests/contracts/ -v --tb=short`. Expected: all real and fake adapters pass the same suite. Contract tests also run nightly against real Zendesk sandbox (cassettes recorded, diffs checked in).

- [ ] **11.2 Implement integration tests for end-to-end message flow** (S1.1–S1.9 integration)
  - **What:** Create `services/api/tests/test_integration_e2e.py` with Testcontainers setup (Postgres + Redis per test). Scenarios:
    - Email ingestion: POST Zendesk webhook → message stored → outbox event → poller consumes → no data loss
    - Chat ingestion: POST /v1/conversations/{id}/messages → 202 → stream connects → message received
    - Coalescing: 5 rapid chat messages → debounce fires → 1 outbox event (batch of 5)
    - Idempotency: same message twice → first returns 202, second returns 409 + same message_id
    - Encryption: message stored encrypted → only tenant DEK can decrypt → cross-tenant access fails
  - **Files:** `services/api/tests/test_integration_e2e.py`
  - **Verify:** Run `pytest services/api/tests/test_integration_e2e.py -v`. Expected: ≥ 95% pass rate. All scenarios pass. Latency p99 < 200ms on ingestion endpoint. No data leakage across tenants.

### Phase 12: Acceptance Tests & J1–J3 Scenarios (Day 9–10)

- [ ] **12.1 Implement acceptance tests for J1 (WISMO email → auto-resolve)** (S1.10)
  - **What:** Create `services/api/tests/acceptance/test_j1_wismo.py`. Scenario: email arrives for known customer (jane@example.com) with simple question ("What's my order status?"). Message ingested → coalesced (no burst) → outbox event → worker receives (logged). Verify: message in database, encrypted, customer identity resolved, awaits triage worker pickup in S2. Test is pending; S2 will add triage run + auto-resolution logic. Verify test structure: given → when → then pattern (BDD-style).
  - **Files:** `services/api/tests/acceptance/test_j1_wismo.py`
  - **Verify:** Run `pytest services/api/tests/acceptance/test_j1_wismo.py -v`. Expected: test passes to "outbox event ready for triage worker" checkpoint. Test is marked `@pytest.mark.xfail(reason="S2: triage graph not yet implemented")` for CI, so sprint doesn't block on it, but structure is in place.

- [ ] **12.2 Implement acceptance tests for J2 (chat coalescing)** (S1.10)
  - **What:** Create `services/api/tests/acceptance/test_j2_coalescing.py`. Scenario: 3 rapid chat messages ("Can I get a refund?", "I bought it last week", "It doesn't work") arrive within 4s. Coalescer debounces, collects all 3 → 1 outbox event with batch. Verify: all 3 messages in database, 1 outbox event (payload = array of 3 message_ids), no duplicate triage runs triggered.
  - **Files:** `services/api/tests/acceptance/test_j2_coalescing.py`
  - **Verify:** Run `pytest services/api/tests/acceptance/test_j2_coalescing.py -v`. Expected: test passes. Assert message_count = 3, outbox event count = 1. 4th message arriving after coalesce window starts new batch.

- [ ] **12.3 Implement acceptance tests for J3 (Zendesk sync)** (S1.10)
  - **What:** Create `services/api/tests/acceptance/test_j3_zendesk_sync.py`. Scenario: Zendesk ticket comment webhook arrives (signed) → parser extracts comment → normalized message → ingested. Verify: message links to conversation + ticket, outbox event queued. S2 will add write-back after triage decision. Test structure: Zendesk webhook POST → verify 200 OK, message row created, outbox event created. Later (S2+): verify write-back to Zendesk sidebar.
  - **Files:** `services/api/tests/acceptance/test_j3_zendesk_sync.py`
  - **Verify:** Run `pytest services/api/tests/acceptance/test_j3_zendesk_sync.py -v`. Expected: webhook processed, message created, outbox event created. No side effects on signature verification failure (400, no data inserted).

### Phase 13: Documentation & CI/CD (Day 10)

- [ ] **13.1 Update CI/CD pipeline for Sprint 1 (unit → integration → acceptance stages)**
  - **What:** Extend `.github/workflows/test.yml`. Add stages: (1) Unit tests (pytest on py_core + api, < 3min, coverage ≥ 80%), (2) Integration tests (Testcontainers, < 10min, RLS audit + contract suites), (3) Acceptance tests (acceptance/ directory, <5min, J1–J3 marked xfail for now). Fail build if coverage < 80% or RLS audit fails. Cache dependencies. Parallelize where safe (per-service unit tests in parallel, then integration sequentially).
  - **Files:** `.github/workflows/test.yml` (extended), `services/api/pyproject.toml` (coverage settings)
  - **Verify:** Commit to feature branch, push to GitHub, verify workflow runs, all stages pass. PR shows coverage % change. Coverage report available as artifact.

- [ ] **13.2 Write API documentation (OpenAPI spec auto-generated from FastAPI)** (Reference for S1 endpoints)
  - **What:** FastAPI auto-generates OpenAPI spec at `/openapi.json`. Add docstrings to all endpoint functions (request/response schema, error codes, examples). Run `fastapi-docs` generator to export `api/docs/openapi.yaml`. Document error codes per RFC 9457 (400 Bad Request, 401 Unauthorized, 404 Not Found, 409 Conflict, 429 Too Many Requests, 500 Internal Server Error). Update `Docs/api.md` with examples: "Ingest a message," "Stream updates," "Verify Zendesk webhook."
  - **Files:** `Docs/api.md`, `services/api/src/triage/api/endpoints/*.py` (docstrings), `.github/workflows/docs.yml` (generate + publish)
  - **Verify:** Start `python -m uvicorn triage.api.main:app`, navigate to `http://localhost:8000/docs` (Swagger UI). Verify all endpoints documented, request/response schemas shown. OpenAPI spec can be imported into Postman.

- [ ] **13.3 Write Sprint 1 README & deployment guide** (Reference for operations)
  - **What:** Create `services/api/README.md` with: architecture diagram (Zendesk → webhook, widget → ingestion endpoint), quick start (docker-compose, install deps, run tests), deployment (container build, env vars, Terraform if applicable), troubleshooting (common errors, log investigation). Create `services/triage_worker/README.md` with: consumer loop, event processing, error handling, metrics. Create `packages/widget/README.md` with: CDN integration example, security (CSP headers), browser support.
  - **Files:** `services/api/README.md`, `services/triage_worker/README.md`, `packages/widget/README.md`
  - **Verify:** Follow README steps, app starts locally, can ingest messages, can stream chat. No missing steps or typos.

---

## Testing Strategy (Tier-based)

| Tier | Component | Testing approach | Tools | Target coverage |
|---|---|---|---|---|
| A (Strict TDD) | Normalizers, Idempotency, Encryption, Identity, Coalescing, Decision matrix | Unit tests written first, property tests for invariants | pytest, Hypothesis | ≥ 90% line |
| B (Contract-first) | API endpoints, webhooks, outbox, fakes | Recorded fixtures, OpenAPI fuzz, consumer contract | Schemathesis, Pact, pytest-recording | 100% coverage of interfaces |
| C (Eval-driven) | PII detection, groundedness | Golden datasets with thresholds, no real LLM | Ragas, DeepEval (mocked via FakeLLM) | Threshold: Presidio recall ≥ 0.95 |
| D (ATDD) | J1–J3 journeys | Gherkin-style acceptance scenarios, marked xfail for S2 dependencies | pytest-bdd, Testcontainers | Scenarios pass end-to-env checkpoint |
| E (Smoke) | Widget bundle, Docker image, IaC | Post-implementation checks | Playwright, Trivy, Docker scan | No blockers; warnings OK |

---

## Verification (Build & Test Commands)

All verification commands assume you are in the workspace root (`d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-`).

**Local development:**
```bash
# Start local stack (Postgres, Redis, MinIO, Mailpit, Langfuse)
make up

# Install dependencies
uv sync

# Run all tests (unit + integration, excludes E2E/evals)
make test

# Run just unit tests (fast feedback loop)
pytest packages/py_core/tests services/api/tests --ignore=services/api/tests/acceptance -m "not integration"

# Run integration tests (includes RLS audit, contract suites)
pytest services/api/tests -m "integration"

# Run acceptance tests (J1–J3 scenarios)
pytest services/api/tests/acceptance -v

# Lint + type check
make lint
mypy --strict packages/py_core services/api

# Coverage report
pytest --cov=py_core --cov=services/api --cov-report=html

# Build widget
cd packages/widget && npm run build

# Check widget bundle size
ls -lh packages/widget/dist/widget.min.js
```

**CI/CD (GitHub Actions):**
```yaml
# Runs on every push to main and PRs:
- Unit tests: pytest (< 3 min)
- Integration tests: pytest (< 10 min)
- Acceptance tests: pytest (< 5 min)
- Lint: ruff, mypy, Trivy
- Coverage: must be ≥ 80% on core modules
- Build artifact: widget bundle, API image
```

**Database migrations:**
```bash
# Apply all pending migrations
alembic -c packages/py_core/alembic.ini upgrade head

# Create new migration
alembic -c packages/py_core/alembic.ini revision --autogenerate -m "add X table"

# Verify RLS policies
pytest packages/py_core/tests/test_rls.py -v
```

---

## Definition of Done (Per Item)

Each implementation item is **done** when:

1. ✅ **Code written** (follows project style, type hints, docstrings)
2. ✅ **Tests written first** (failing → passing, ≥ 90% coverage for Tier A)
3. ✅ **Builds locally** (`make test` passes, no errors/warnings from mypy/ruff)
4. ✅ **Tenant isolation verified** (if DB access: RLS tests pass, cross-tenant access blocked)
5. ✅ **Logging redacts PII** (sensitive data never in logs; grep for PERSON, PHONE_NUMBER → no matches)
6. ✅ **Dependency chain satisfied** (all upstream items complete, no circular deps)
7. ✅ **Git commit** (atomic, descriptive message, no incomplete WIP pushes to main)
8. ✅ **PR or branch** (linked to issue tracker if applicable; code review before merge)

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Idempotency key collisions** | Low | High (duplicate messages) | Property tests with Hypothesis; hash function review; collision monitoring |
| **Encryption key loss** | Low | Critical (data unrecoverable) | KMS key lifecycle; automated key rotation; backups of KEK; incident runbook |
| **Cross-tenant data leak** | Very low | Critical (compliance breach) | Mandatory RLS audit on every migration; test every table with dual tenants; penetration testing |
| **Zendesk webhook signature replay** | Low | Medium (false triage) | Nonce tracking; timestamp validation (< 5min old); replay detection |
| **Message loss on worker crash** | Medium | High (customer impact) | Transactional outbox; at-least-once delivery; consumer deduping; circuit breaker on dead-letter |
| **PII leaked in logs** | Medium | High (compliance breach) | Structured logging with PII redaction; grep audit; secrets scanning in CI |
| **Widget bundle size > 40KB** | Low | Medium (performance) | Continuous bundle tracking; esbuild strict size budget; pre-commit hook |
| **Latency > 200ms p99** | Medium | Medium (UX) | Load testing early; profiling; caching; database indexes; Redis connection pooling |

---

## Success Metrics (Sprint 1 Exit Gate)

✅ **All deliverables implemented:**
- S1.1 Message normalization (4 normalizers, idempotency manager)
- S1.2 Ingestion endpoint (202 Accepted, SSE streaming)
- S1.3 Zendesk webhook receiver (signature verified, write-back ready)
- S1.4 Message coalescing (debounce, Redis lock)
- S1.5 Identity resolution (merge, IAL1)
- S1.6 Encryption + PII (AES-256-GCM, Presidio)
- S1.7 Outbox writer (transactional, poller)
- S1.8 Chat widget v0 (Preact, SSE client, accessible)
- S1.9 Conversation model (ORM, queries, RLS)
- S1.10 Acceptance gate (J1–J3 scenarios structure in place)

✅ **Test coverage:**
- Unit tests: ≥ 90% on core modules (normalizers, idempotency, encryption, identity, coalescing, outbox)
- Integration tests: 100% of API endpoints + contract suites
- Acceptance tests: J1–J3 checkpoint tests structure (tests marked xfail for S2 dependencies)
- RLS audit: all tables pass cross-tenant isolation test
- Coverage report: ≥ 80% overall

✅ **Performance:**
- Ingestion latency: p99 < 200ms (202 response time)
- Widget bundle: < 40KB gzipped
- Outbox polling: events processed within 1s of insertion
- Database queries: all critical paths indexed

✅ **Security & compliance:**
- Zero PII in logs (grep audit passed)
- Tenant isolation: RLS + composite keys
- Encryption: AES-256-GCM, DEK versioned
- Audit trail: append-only, hash-chained
- No known vulnerabilities: Trivy + Semgrep pass

✅ **Operational readiness:**
- Local dev stack: `make up` → ready in < 1 min
- CI/CD: all tests automated, PR gates enforced
- Documentation: API docs (OpenAPI), README, troubleshooting
- Instrumentation: structured logs, OpenTelemetry traces, Langfuse recording (ready for S2)

✅ **Design review:**
- Architecture reviewed (tenancy, outbox, encryption, RLS)
- API contract stable (OpenAPI spec)
- Database schema frozen (Alembic migrations applied)
- Widget accessibility audit passed (axe-core, WCAG AA)

---

## Timeline (Gantt summary)

```
Sprint 1 Implementation (2 weeks)
│
├─ Day 1–0.5: Database & Testing Foundation (Phase 0)
│  └─ RLS policies, Testcontainers fixtures, Fakes
│
├─ Day 1–2: Normalization & Idempotency (Phase 1)
│  └─ CanonicalMessage, Normalizers, IdempotencyManager
│
├─ Day 2–3: Encryption & PII (Phase 2)
│  └─ EnvelopeEncryption, PiiHandler, Presidio
│
├─ Day 3: Identity Resolution (Phase 3)
│  └─ IdentityResolver, Merge, IAL1
│
├─ Day 3–4: Coalescing & Locking (Phase 4)
│  └─ MessageCoalescer, Redis, Debounce
│
├─ Day 4: Outbox Writer (Phase 5)
│  └─ OutboxWriter, OutboxPoller, Contract Tests
│
├─ Day 4–5: Zendesk Webhook (Phase 6)
│  └─ Signature Verification, Event Routing, Write-Back
│
├─ Day 5–6: Ingestion Endpoint & Streaming (Phase 7)
│  └─ POST /v1/conversations/{id}/messages, SSE
│
├─ Day 6–7: Chat Widget (Phase 8)
│  └─ Preact Component, SSE Client, Accessibility
│
├─ Day 7: Conversation Model (Phase 9)
│  └─ ORM, Queries, RLS, Migration
│
├─ Day 7–8: FastAPI & Worker (Phase 10)
│  └─ App Skeleton, Middleware, Triage Worker
│
├─ Day 8–9: Integration Tests & Contracts (Phase 11)
│  └─ End-to-End Tests, Contract Suites
│
├─ Day 9–10: Acceptance Tests (Phase 12)
│  └─ J1–J3 Scenarios, BDD-style
│
└─ Day 10: Documentation & CI/CD (Phase 13)
   └─ API Docs, README, GitHub Actions
```

**Effort distribution:**
- Core ingestion pipeline (phases 1–5): 50%
- Endpoints & streaming (phases 7, 10): 20%
- Widget (phase 8): 15%
- Testing & documentation (phases 11–13): 15%

---

## Post-Sprint 1 Handoff to Sprint 2

Sprint 1 **complete** when all items above are **done**. Sprint 2 begins with:
- ✅ Message ingestion pipeline working (all messages reach database encrypted, de-duplicated, logged to outbox)
- ✅ Chat widget live (embedded in test page, real-time SSE working)
- ✅ Zendesk webhook receiver ready (write-back logic stubbed, ready for S2 triage decision)
- ✅ Outbox poller consuming events (background task queue ready for S2 triage graph)
- ✅ Acceptance test structure in place (J1–J3 scenarios marked xfail, ready for S2 triage implementation)

Sprint 2 will implement:
- LangGraph triage graph (15 nodes, decision matrix, classification)
- Knowledge module (RAG retrieval, composition, guards)
- Tools & write actions (dry-run in MVP)

---

**Document version:** 1.0  
**Status:** Ready for implementation  
**Approval:** [Product Lead], [Engineering Lead] (to be signed off in GitHub PR)

