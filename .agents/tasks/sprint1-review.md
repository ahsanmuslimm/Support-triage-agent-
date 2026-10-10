# Sprint 1 Message Ingestion Pipeline — Semantic Code Review

**Verdict: NEEDS_CHANGES**

Sprint 1 implements all 10 core deliverables as standalone Python modules with comprehensive unit test coverage (42 tests, 100% passing). The architecture is modular and testable, with correct design patterns for encryption, PII handling, identity deduplication, and webhook verification. However, three critical architectural invariants are violated: database persistence has not been implemented, which breaks idempotency enforcement, outbox transactionality, and tenant isolation via RLS. The 202 Accepted ingestion endpoints and SSE streaming are stubbed. The triage worker lacks database integration. These are not minor TODOs—they are fundamental gaps that prevent any real message flow through the system.

**Watch for:**
- Database schema (Alembic migrations 0003+) does not exist; all persistence is in-memory only. (**confirmed**) Idempotency cannot be enforced across server restarts. Outbox events cannot be durably stored.
- Tenant isolation relies on in-memory scoped indexes in `IdentityResolver`, not RLS policies. Cross-tenant data leakage is architecturally possible if identity resolution queries are ever centralized. (**confirmed**)
- Encryption key management is stubbed: init from `ENCRYPTION_KEY` env var with no key versioning or rotation API. DEK/KEK separation is mentioned in docs but not implemented. (**likely**)
- The ingestion endpoint (S1.2) persists nothing to database; message storage is TODO. Same for conversation model—ORM exists but queries are stubbed. (**confirmed**)
- SSE streaming endpoint heartbeats 10 times then closes; real subscription to new messages is not wired. (**confirmed**)

**Verdict: NEEDS_CHANGES** — Implement database schema with RLS, connect domain writes to outbox writer in same transaction, integrate identity and coalescing logic into ingestion pipeline, and implement streaming subscriptions before this can be considered a working ingestion layer.

---

## High-level View

The implementation separates concerns into clean layers: data models (Pydantic), normalizers (channel-specific logic), security (encryption/PII/identity), and durability (outbox). Unit tests verify each layer in isolation and confirm 90% code coverage. However, the system is missing the database schema that connects these layers into a working pipeline. Messages are normalized and validated but never persisted; the idempotency manager generates keys but has no table to query; the outbox writer collects events in memory but has no way to poll or deliver them; conversations and streaming are API stubs.

The identity resolver correctly deduplicates customers by email/phone/Zendesk ID with tenant-scoped in-memory indexes, but in production this must use database queries with RLS policies. The Zendesk webhook handler verifies signatures correctly and normalizes payloads to `CanonicalMessage`, but the message never reaches the database. Encryption is implemented as a standalone module (Fernet, AES-128-CBC) but is not integrated into the message persistence layer. PII detection uses regex patterns (email, phone, credit card, SSN) and deterministic token generation, but redaction is not called in the ingestion pipeline—plaintext messages are stored to in-memory structures unchanged.

To reach production readiness, the review criteria require: (1) database schema with tenant_id in all composite keys and RLS enforcement, (2) outbox events written atomically in the same transaction as messages, (3) idempotency enforcement at ingestion time (409 on duplicate), (4) identity resolution queries backed by database, (5) PII redaction applied before any downstream processing, (6) coalescing locks via Redis, (7) SSE real-time subscriptions. None of the above integrate with the database; all are stubbed.

---

<details>
<summary>Issues (9)</summary>

1. **Database schema and migrations missing** — No Alembic migration (0003+) creates `messages`, `conversations`, `customers`, `outbox`, or `vault.pii_tokens` tables. Idempotency cannot be enforced, outbox events cannot be durable, identity resolution cannot use database indexes, and messages are never persisted. Add `packages/py_core/alembic/versions/0003_sprint1_tables.py` with composite keys (tenant_id, id), RLS policies on every table, and unique index on (tenant_id, idempotency_key) on messages table.

2. **Idempotency not enforced at ingestion** — `POST /api/v1/conversations/{id}/messages` generates an idempotency key but never checks the database for duplicates. No 409 Conflict is returned on second receipt of same message. The TODO comment says "Check for duplicate (would return 409 Conflict if duplicate)" but the check is not implemented. Implement check_idempotency() to query messages table by idempotency_key; on match, return 409 with Location header pointing to original.

3. **Outbox events stored in memory, not database** — `OutboxWriter.write_event()` appends to `self._in_memory_events` list. On server restart, all pending events are lost. Guarantee says "Every message insert triggers an outbox event in the same transaction"—this is not transactional (no database transaction), and events are not durable. Implement `write_event()` to INSERT into outbox table in same SQLAlchemy transaction as message INSERT; wrap in session.begin() block.

4. **Tenant isolation relies on in-memory indexes, not RLS** — `IdentityResolver` maintains `_email_index[tenant_id]` dict and `_phone_index[tenant_id]` dict in memory. On second server instance or after restart, these indexes vanish. A code path that bypasses the resolver and queries customers directly has no RLS policy to prevent cross-tenant leakage. Add RLS policies to customers table: `CREATE POLICY customers_tenant_isolation ON customers USING (tenant_id = CURRENT_SETTING('app.tenant_id')::UUID)`. Refactor resolver to query database.

5. **Encryption key versioning not implemented** — `EnvelopeEncryption.__init__()` loads a single key from `ENCRYPTION_KEY` env var and sets `self.dek_version = 1` as a constant. No API to rotate keys, no versioned key store, no ability to decrypt messages encrypted with old DEK versions. Implement key versioning: store DEK versions in database with created_at/revoked_at; on decrypt, fetch the versioned DEK from database using the dek_version field from encrypted payload.

6. **Encryption not integrated into message persistence** — The `ingest_message()` endpoint has a TODO comment "TODO: Encrypt body" but does not call `EnvelopeEncryption.encrypt()`. Messages are stored (in memory) with plaintext bodies. Plaintext bodies may reach logging, LLM prompts, or other downstream systems before encryption is applied. Call `EnvelopeEncryption.encrypt(canonical_message.body)` before storing message; store encrypted payload as JSON {"ciphertext": ..., "dek_version": ...} in messages.body_encrypted column.

7. **PII redaction not applied in ingestion** — The `ingest_message()` endpoint has a TODO comment "TODO: Redact PII" but does not call `PiiHandler.redact()`. Messages containing emails, phone numbers, credit cards, or SSNs are stored to memory without redaction. Plaintext PII reaches logging and downstream systems. Call `PiiHandler.redact(canonical_message.body)` to return (redacted_text, entities, vault_mapping); store redacted_text in message body, vault_mapping in pii_tokens table.

8. **Real-time SSE streaming not implemented** — `GET /api/v1/streams/conversations/{id}` has a stub `event_generator()` that yields 10 heartbeats then closes. No database query fetches existing messages; no Redis Pub/Sub or AsyncIO queue subscribes to new messages. Client cannot receive real-time updates. Implement: (1) query messages table for conversation_id, serialize as SSE events, (2) create Redis Pub/Sub subscription on channel `conv:{conversation_id}` for new messages, (3) publish to Pub/Sub channel on message ingest, (4) stream events to client with proper line format (`data: {...}\n\n`).

9. **Coalescing, identity resolution, and PII redaction not wired into pipeline** — The ingestion endpoint creates a `CanonicalMessage` and immediately returns 202. It does not call `IdentityResolver.resolve_or_create()`, `MessageCoalescer.queue_message()`, or `PiiHandler.redact()`. The normalizers, identity resolver, and PII handler are tested in isolation but never compose into a working message flow. The endpoint TODO comments list all the missing steps in order. Implement the full pipeline: normalize → validate → encrypt → redact PII → resolve identity → coalesce → write message + outbox event in transaction.

</details>

---

## Database Schema & Persistence

The specification requires every table to have (tenant_id, id) as composite primary key with RLS policies. The implementation has Pydantic models but Alembic migrations do not exist. Only Sprint 0 migrations exist (0001 baseline, 0002 audit hash chain). No 0003 migration for S1.1–S1.9 tables.

Idempotency keys are generated but never checked against a database index. Messages are normalized but stored to in-memory lists. The `IdempotencyManager.check_idempotency()` method is never called. Outbox events are collected in memory and lost on server restart. The identity resolver maintains in-memory dicts that evaporate on redeployment. None of this is durable or scalable across multiple server instances. The `OutboxWriter.write_event()` method has a TODO: "Write to database in same transaction as domain object." This is a critical architectural requirement that is not met.

---

## Idempotency & Duplicate Detection

`IdempotencyManager` generates deterministic keys from `tenant_id`, `provider_message_id` (priority 1) or `sender_id + body_hash` (priority 2). Tests confirm the key is deterministic.

However, the ingestion endpoint does not query the database on ingest. The code has a TODO comment "Check for duplicate (would return 409 Conflict if duplicate)" but never implements it. Every POST request returns 202 even if the same message was ingested moments before. Clients will retry on timeout and get 202 again, resulting in duplicates. The 409 response code and Location header are documented in tests but not implemented.

---

## Encryption & Key Management

The `EnvelopeEncryption` class implements Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) correctly. Round-trip tests pass; attempting to decrypt with a different key raises `RuntimeError`.

However, key management is incomplete. A single master key is loaded from `ENCRYPTION_KEY` env var; `dek_version` is hardcoded to 1. There is no versioning API, no database of DEK versions, and no way to rotate keys. If the master key is compromised, all historical messages are exposed. If rotation is needed (compliance requirement), there is no mechanism to re-encrypt old messages or decrypt messages encrypted with old keys.

Encryption is not integrated into the message persistence layer. The `ingest_message()` endpoint has a TODO comment "TODO: Encrypt body" but does not call `EnvelopeEncryption.encrypt()`. Message bodies reach logging and downstream systems in plaintext. The plan mentions DEK/KEK separation (local DEK per tenant, KMS-managed KEK), but the implementation conflates them into a single Fernet key.

---

## PII Detection & Redaction

The `PiiHandler` implements regex-based detection for EMAIL, PHONE, CREDIT_CARD, and SSN patterns with deterministic token generation and vault mapping. Patterns are basic but functional for test cases; they miss international formats (IBAN, international phone) and have false-positive risk (any 16-digit sequence looks like a credit card).

However, redaction is not called in the ingestion pipeline. The endpoint normalizes messages but never calls `PiiHandler.redact()`. Plaintext PII reaches logging and downstream systems. Presidio is mentioned in the plan but not integrated.

---

## Identity Resolution & Deduplication

The `IdentityResolver` deduplicates customers across channels using email, phone, and Zendesk ID as lookup keys with tenant-scoped in-memory indexes. Tests confirm correct behavior: same email resolves to same customer, merging across channels works, cross-tenant isolation is enforced.

However, tenant isolation at the in-memory index level is fragile. If the resolver is bypassed and customers are queried directly, there is no RLS policy to enforce isolation. In production, the resolver must query a database table with RLS policies. Identity resolution is not wired into the ingestion pipeline. The `ingest_message()` endpoint has a TODO comment but does not call `IdentityResolver.resolve_or_create()`. No customer record is created or linked to the message.

---

## Zendesk Webhook Handler

The `ZendeskWebhookHandler` verifies HMAC-SHA256 signatures correctly using timing-safe comparison, and normalizes payloads to `CanonicalMessage`. However, the message extracted from the webhook is never persisted to the database (no ingestion integration). Write-back (posting results to Zendesk) and S3 audit trails are TODO.

---

## Conversation Model & Status Tracking

The `Conversation` Pydantic model is well-designed and captures the full lifecycle (status, priority, subject, message count, intent classification, auto-resolution, timestamps). However, the ORM mapping is not implemented. There is no SQLAlchemy `Table` definition, no migrations to create the conversations table, and no database queries. The API endpoints are stubs. Conversation creation is not wired into the ingestion pipeline.

---

## Message Coalescing & Outbox

The `MessageCoalescer` class defines debounce intervals per channel (email: 0s, web_chat: 4s, zendesk: 0s, api: 2s) but is not implemented. `queue_message()` has a TODO comment and does nothing; Redis locks are not wired.

The `OutboxWriter` and `OutboxPoller` implement the transactional outbox pattern only in outline. `write_event()` appends to an in-memory list; on server restart, events vanish. The architectural requirement—every domain object insert must trigger an outbox event in the same SQLAlchemy transaction—is not met. There is no atomicity, no durability, and no guarantee of exactly-once delivery. Neither coalescing nor outbox are wired into the ingestion pipeline; TODO comments list all the missing steps.

---

## Real-time Streaming (SSE)

The `GET /api/v1/streams/conversations/{id}` endpoint returns a `StreamingResponse` with correct SSE headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`). However, the event generator is a stub. It yields 10 heartbeats and closes. There is no database query to fetch existing messages, no subscription mechanism (Redis Pub/Sub or AsyncIO queue) to stream new messages, and no publishing on message ingest.

---

## Test Coverage & Code Quality

The test suite includes 42 tests across five modules, all passing. Code coverage is approximately 90% on core modules. Tests are well-written with descriptive names and both happy and sad paths.

However, tests are unit tests that mock external dependencies (database, Redis, Pub/Sub). There are no integration tests verifying the end-to-end flow: POST message → normalize → check idempotency → encrypt → redact PII → resolve identity → store database → write outbox event → trigger triage worker. Acceptance test scenarios (J1, J2, J3) are documented but not implemented.

---



---

## Recommendations

1. **Create Alembic migration 0003** for Sprint 1 tables (messages, conversations, customers, outbox, pii_tokens, vault). Include composite keys (tenant_id, id), RLS policies, and indexes on idempotency_key, email_hash, phone_hash, customer_id.

2. **Implement message persistence** in `ingest_message()`: Insert CanonicalMessage to messages table in a transaction, immediately write OutboxEvent to outbox table in the same transaction, return 202 only after both succeed.

3. **Implement idempotency check** before message insert: Query messages table by idempotency_key; on match, return 409 with Location header.

4. **Integrate encryption** into the pipeline: Call `EnvelopeEncryption.encrypt(message.body)` before insert, store encrypted payload (JSON) in messages.body_encrypted, store plaintext in messages.body only if decrypted on read.

5. **Integrate PII redaction** into the pipeline: Call `PiiHandler.redact(message.body)` after normalization, store redacted body in messages.body, store vault mapping in pii_tokens table.

6. **Integrate identity resolution** into the pipeline: Call `IdentityResolver.resolve_or_create()` with sender email/phone, link resolved customer_id to message and conversation.

7. **Implement Redis coalescing**: Add Redis locks on conversation_id, debounce timers per channel, and batching logic to prevent duplicate triage runs.

8. **Implement real-time streaming**: Query messages from database on SSE connection open, subscribe to Redis Pub/Sub on conversation_id for new messages, publish to channel on message ingest.

9. **Add integration tests** for end-to-end scenarios (J1 WISMO email, J2 chat burst coalescing, J3 Zendesk write-back) using Testcontainers for PostgreSQL and Redis.

---

## Summary

Sprint 1 has delivered well-architected, thoroughly tested modules for message normalization, encryption, PII handling, identity resolution, and webhook verification. The code quality is high, and the security patterns are sound. However, the system is not functional as a complete ingestion pipeline because the database schema does not exist, persistence is in-memory only, idempotency cannot be enforced, encryption and PII redaction are not integrated, and real-time streaming is stubbed. These are not minor gaps—they are fundamental architectural requirements. Until the database layer is connected, messages cannot flow through the system durably or reliably, tenant isolation is not enforced, and the acceptance criteria cannot be met.

The implementation is ready for Sprint 2, which should focus on Alembic migrations, database integration, and end-to-end testing. The modular design makes this straightforward: wire up each module's TODO comments in order, add the outbox event write to the transaction, and the pipeline should work.
