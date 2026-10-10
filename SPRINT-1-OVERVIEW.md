# Sprint 1 - Ingestion & Conversation Core (Overview)

## Objective
Build the complete message ingestion pipeline: normalize messages from all channels, enforce idempotency, handle bursts via coalescing, and implement Zendesk bidirectional sync.

## Sprint 1 Deliverables (10 Items)

| # | Deliverable | Status | Focus |
|---|---|---|---|
| **1.1** | Message Normalization Model | ✅ DOCUMENTED | Canonical message + normalizers |
| **1.2** | Message Ingestion Endpoint | ✅ DOCUMENTED | POST /v1/conversations/{id}/messages (202) |
| **1.3** | Zendesk Webhook Receiver | 🔄 IN PROGRESS | Signed webhooks, write-back |
| **1.4** | Message Coalescing | 📋 PLANNED | Debounce, conversation lock |
| **1.5** | Identity Resolution | 📋 PLANNED | Email/phone/external ID merging |
| **1.6** | Encryption & PII | 📋 PLANNED | Envelope encryption, pseudonymization vault |
| **1.7** | Outbox Writer | 📋 PLANNED | Event durability for async processing |
| **1.8** | Chat Widget v0 | 📋 PLANNED | Preact SSE stream, accessibility |
| **1.9** | Conversation Model | 📋 PLANNED | DB model, status tracking |
| **1.10** | S1 Acceptance Gate | 📋 PLANNED | Test coverage, J1 scenario partial pass |

---

## What's Documented So Far

### S1.1 - Message Normalization & Model
✅ **Complete implementation for:**
- `CanonicalMessage` Pydantic model (all fields for all channels)
- `EmailNormalizer` (threading via Message-ID)
- `WebChatNormalizer`
- `ZendeskNormalizer`
- `NormalizerFactory` (plugin pattern)
- `IdempotencyManager` (exactly-once semantics)
- Full unit test suite

**Key Features:**
- Unified message model across email, chat, Zendesk, Intercom, WhatsApp
- Provider message IDs for external deduplication
- Email threading (In-Reply-To, References)
- Idempotency keys (deterministic based on provider ID or content hash)
- Attachment metadata
- Channel-specific metadata preservation

**Tests Included:**
- Email normalization with subject + body
- Email threading detection
- Web chat conversion
- Zendesk comment handling
- Idempotency key generation
- Duplicate detection

---

### S1.2 - Message Ingestion Endpoint
✅ **Complete implementation for:**
- `POST /v1/conversations/{conversation_id}/messages` (returns 202)
- `GET /v1/streams/conversations/{conversation_id}` (SSE stream)
- `GET /v1/conversations/{conversation_id}/messages` (list, paginated)
- Background task queuing for triage
- Idempotency-Key header handling
- Outbox writer for event durability

**FastAPI Structure:**
- Router-based organization
- Dependency injection for tenant context
- Async background tasks
- Streaming responses (SSE)

**Integration Tests:**
- 202 Accepted response with stream URL
- 409 Conflict on duplicate idempotency key
- Message persistence before response
- List messages with pagination

---

## Architecture (Sprint 1)

```
┌─────────────────────────────────────────┐
│         INBOUND CHANNELS                │
│  Email  Chat  Zendesk  Slack  API      │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│     MESSAGE INGESTION (S1.2)             │
│  POST /v1/conversations/{id}/messages   │
│  - 202 Accepted                         │
│  - Idempotency-Key header              │
│  - SSE stream URL                       │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  NORMALIZATION (S1.1)                    │
│  - CanonicalMessage model               │
│  - Channel-specific normalizers         │
│  - Provider message ID extraction       │
│  - Email threading detection            │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  COALESCING (S1.4)                       │
│  - Debounce (4s chat, 0s email)         │
│  - Conversation lock + heartbeat        │
│  - Cancel at node boundary              │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  IDENTITY RESOLUTION (S1.5)              │
│  - Email/phone/external ID merge        │
│  - IAL1 (channel-asserted)              │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  ENCRYPTION & PII (S1.6)                 │
│  - Envelope encryption (DEK + KEK)      │
│  - Presidio pseudonymization            │
│  - Vault token storage                  │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  OUTBOX WRITER (S1.7)                    │
│  - Durable event persistence            │
│  - Per-conversation ordering            │
│  - Poller for async processing          │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  TRIAGE WORKER (S2+)                     │
│  (Message queued for classification)    │
└─────────────────────────────────────────┘
```

---

## Key Decisions Made

| Decision | Rationale |
|---|---|
| **202 Accepted** | Message persisted durably; client gets response immediately |
| **Idempotency-Key header** | HTTP standard for exactly-once semantics |
| **SSE streams** | Real-time updates without websocket complexity |
| **Transactional outbox** | Ensures no message loss; works without Kafka initially |
| **Per-channel normalizers** | Captures channel-specific semantics (threading, etc.) |
| **Envelope encryption** | Separates data at-rest encryption from PII handling |

---

## Testing Strategy (Sprint 1)

### Unit Tests (Tier A - Strict TDD)
- Normalizers handle all channel formats
- Idempotency keys are deterministic
- Email threading detection
- Body hash consistency

### Integration Tests (Tier B - Contract-first)
- POST endpoint returns 202 with stream URL
- 409 Conflict on duplicate idempotency key
- Message persisted before response
- Outbox event created
- RLS enforced (tenant isolation)

### Acceptance Tests (Tier D - ATDD)
- J1 (WISMO) starts → message ingested → queued for triage
- Email threading preserved across multiple messages
- Duplicate messages detected and rejected

---

## Remaining Work (S1.3–S1.10)

After S1.1 and S1.2 are complete:

**S1.3 – Zendesk Webhook** (2 days)
- Signed webhook receiver
- Comment ingestion
- Write-back to Zendesk sidebar

**S1.4 – Coalescing** (2 days)
- Redis debounce
- Conversation lock with heartbeat
- Cancel-at-node-boundary on new message

**S1.5 – Identity Resolution** (2 days)
- Email/phone/external ID merging
- Merge validation (no cross-tenant)
- IAL assignment per channel

**S1.6 – Encryption & PII** (3 days)
- Envelope encryption (DEK per tenant)
- Presidio integration
- Vault for pseudo-anonymization

**S1.7 – Outbox Writer** (1 day)
- Transactional writes
- Event poller
- At-least-once guarantee

**S1.8 – Chat Widget v0** (3 days)
- Preact component
- SSE streaming
- WCAG 2.2 AA accessibility

**S1.9 – Conversation Model** (1 day)
- Conversation table queries
- Status tracking
- Escalation triggers

**S1.10 – S1 Gate** (1 day)
- Test all 10 items
- J1 scenario flows to triage worker
- 100% coverage on core domain

---

## Success Criteria for Sprint 1

✓ **All 10 deliverables implemented and tested**  
✓ **Message ingestion endpoint returns 202 + stream URL**  
✓ **Idempotency enforced (409 on duplicate)**  
✓ **J1 (WISMO) scenario flows end-to-end to triage worker**  
✓ **Zero message loss (transactional outbox)**  
✓ **Tenant isolation verified (RLS working)**  
✓ **Email threading preserved across replies**  
✓ **All 10 acceptance scenarios still @pending but setup complete**  

---

## Integration with Sprint 0

Sprint 1 depends on Sprint 0:
- ✅ PostgreSQL schema (18 tables, including messages table)
- ✅ Tenant context enforcement (@require_tenant)
- ✅ RFC 9457 error responses
- ✅ Structured logging with PII redaction
- ✅ Docker Compose (PostgreSQL, Redis, MinIO)
- ✅ CI/CD pipeline (tests run automatically)

Sprint 1 unblocks Sprint 2:
- 🔄 Message ingestion complete
- 📋 Conversation model ready
- 📋 Triage worker can consume messages from outbox

---

## File Structure After Sprint 1

```
packages/api/src/triage/
├── models/
│   └── message.py              # S1.1 ✅
├── ingestion/
│   ├── normalizers.py          # S1.1 ✅
│   ├── idempotency.py          # S1.1 ✅
│   ├── coalescing.py           # S1.4 (TBD)
│   ├── identity.py             # S1.5 (TBD)
│   └── encryption.py           # S1.6 (TBD)
├── api/
│   ├── main.py                 # S1.2 ✅
│   ├── endpoints/
│   │   ├── messages.py         # S1.2 ✅
│   │   ├── conversations.py    # S1.9 (TBD)
│   │   └── webhooks.py         # S1.3 (TBD)
│   └── middleware/
│       └── auth.py             # (TBD)
└── tests/
    ├── test_normalization.py   # S1.1 ✅
    └── test_ingestion.py       # S1.2 ✅

packages/widget/src/
└── widget.tsx                  # S1.8 (TBD)
```

---

**Status:** Sprint 1 foundation documented and committed.  
**Next:** Continue with S1.3–S1.10 or begin implementation.  
**Timeline:** ~2 weeks (2-week sprints per plan)
