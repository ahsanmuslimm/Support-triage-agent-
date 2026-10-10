# Sprint 1 - Ingestion & Conversation Core (Overview)

## Objective
Build the complete message ingestion pipeline: normalize messages from all channels, enforce idempotency, handle bursts via coalescing, and implement Zendesk bidirectional sync.

## Sprint 1 Deliverables (10 Items)

| # | Deliverable | Status | Focus |
|---|---|---|---|
| **1.1** | Message Normalization Model | ✅ DOCUMENTED | Canonical message + normalizers |
| **1.2** | Message Ingestion Endpoint | ✅ DOCUMENTED | POST /v1/conversations/{id}/messages (202) |
| **1.3** | Zendesk Webhook Receiver | ✅ DOCUMENTED | Signed webhooks, write-back |
| **1.4** | Message Coalescing | ✅ DOCUMENTED | Debounce, conversation lock |
| **1.5** | Identity Resolution | ✅ DOCUMENTED | Email/phone/external ID merging |
| **1.6** | Encryption & PII | ✅ DOCUMENTED | Envelope encryption, pseudonymization vault |
| **1.7** | Outbox Writer | ✅ DOCUMENTED | Event durability for async processing |
| **1.8** | Chat Widget v0 | ✅ DOCUMENTED | Preact SSE stream, accessibility |
| **1.9** | Conversation Model | ✅ DOCUMENTED | DB model, status tracking |
| **1.10** | S1 Acceptance Gate | ✅ DOCUMENTED | Test coverage, J1-J3 scenarios, sign-off |

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

## All Sprint 1 Items (S1.1–S1.10)

### S1.1 – Message Normalization & Model ✅ DONE
- `CanonicalMessage` Pydantic model
- Channel-specific normalizers (Email, Chat, Zendesk, SMS)
- Email threading (Message-ID, References)
- Idempotency keys (deterministic)
- Attachment metadata handling
- Full unit test suite (~450 lines)

### S1.2 – Message Ingestion Endpoint ✅ DONE
- `POST /v1/conversations/{conversation_id}/messages` (202 Accepted)
- `GET /v1/streams/conversations/{conversation_id}` (SSE)
- `GET /v1/conversations/{conversation_id}/messages` (paginated list)
- Idempotency-Key header handling
- Background task queuing
- Full integration test suite (~400 lines)

### S1.3 – Zendesk Webhook Receiver ✅ DOCUMENTED
- HMAC-SHA256 signature verification
- Event type routing (ticket.created, comment.created, status_changed)
- Write-back to Zendesk ticket sidebars
- Idempotency enforcement
- Rate limiting & backpressure
- **Effort:** 2 days | **Lines:** ~450

### S1.4 – Message Coalescing ✅ DOCUMENTED
- Redis-based conversation locking
- Debounce timers (4s chat, 0s email, 2s SMS)
- Message coalescing (concatenation or thread view)
- At-node-boundary cancellation
- Deadlock prevention (30s TTL)
- **Effort:** 2 days | **Lines:** ~400

### S1.5 – Identity Resolution ✅ DOCUMENTED
- Email/phone/external ID merging
- Customer deduplication
- IAL (Identity Assurance Level) tracking
- Cross-tenant isolation (RLS)
- Identity aliases (email_alias, phone_alias)
- **Effort:** 2 days | **Lines:** ~400

### S1.6 – Encryption & PII Handling ✅ DOCUMENTED
- Envelope encryption (AES-256-GCM, DEK/KEK)
- Microsoft Presidio integration (PII detection)
- Pseudonymization vault (token storage)
- Audit logging (PII access trail)
- Key rotation support
- Customer privacy settings (opt-out, anonymization)
- **Effort:** 3 days | **Lines:** ~500

### S1.7 – Outbox Writer ✅ DOCUMENTED
- Transactional outbox pattern
- Event durability (no message loss)
- Outbox poller (background task)
- Retry logic (exponential backoff)
- Dead letter queue (DLQ) handling
- Publisher interface (Kafka, HTTP, in-memory)
- **Effort:** 1 day | **Lines:** ~350

### S1.8 – Chat Widget v0 ✅ DOCUMENTED
- Preact component (no external dependencies)
- SSE streaming (real-time messages)
- Message input + send
- Accessibility (WCAG 2.2 AA)
  - Keyboard navigation (Tab, Enter, Escape)
  - Screen reader support (aria-live, aria-label)
  - Color contrast ≥ AA
  - Focus indicators
- Responsive design (mobile + desktop)
- < 50KB bundle (gzipped)
- **Effort:** 3 days | **Lines:** ~600 (HTML/CSS/TS)

### S1.9 – Conversation Model ✅ DOCUMENTED
- `Conversation` ORM model (status, priority, SLA tracking)
- Status state machine (open → pending → resolved → escalated)
- SLA tracking (response + resolution times)
- Denormalized fields (message_count, unread_count)
- Query helpers (open conversations, at-risk, assigned)
- Multi-tenancy + RLS enforcement
- **Effort:** 1 day | **Lines:** ~300

### S1.10 – Sprint 1 Acceptance Gate ✅ DOCUMENTED
- Test coverage verification (≥ 80% unit, 100% integration)
- Acceptance scenarios (J1–J3):
  - **J1:** WISMO auto-resolution (email inquiry → auto-resolved)
  - **J2:** Chat coalescing (3 messages → 1 triage job)
  - **J3:** Zendesk sync (ticket comment → triage → write-back)
- Performance benchmarks (< 200ms p99 ingestion latency)
- Security checklist (RLS, encryption, audit logging)
- Sign-off criteria (product, engineering, QA)
- **Effort:** 1 day | **Lines:** ~500 (spec + test code)

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

## Effort Estimate

| Item | Effort | Status |
|---|---|---|
| S1.1 | 2 days | ✅ DONE (code in py_core) |
| S1.2 | 2 days | ✅ DONE (code in py_core) |
| S1.3 | 2 days | 📋 DOCUMENTED |
| S1.4 | 2 days | 📋 DOCUMENTED |
| S1.5 | 2 days | 📋 DOCUMENTED |
| S1.6 | 3 days | 📋 DOCUMENTED |
| S1.7 | 1 day | 📋 DOCUMENTED |
| S1.8 | 3 days | 📋 DOCUMENTED |
| S1.9 | 1 day | 📋 DOCUMENTED |
| S1.10 | 1 day | 📋 DOCUMENTED |
| **Total** | **19 days** | ~2 weeks (2-week sprint) |

---

## Documentation Output

**Files Created:**
- ✅ S1.1-Message-Normalization-and-Model.md (450 lines)
- ✅ S1.2-Message-Ingestion-Endpoint.md (400 lines)
- ✅ S1.3-Zendesk-Webhook-Receiver.md (450 lines)
- ✅ S1.4-Message-Coalescing.md (400 lines)
- ✅ S1.5-Identity-Resolution.md (400 lines)
- ✅ S1.6-Encryption-and-PII-Handling.md (500 lines)
- ✅ S1.7-Outbox-Writer.md (350 lines)
- ✅ S1.8-Chat-Widget-v0.md (600 lines)
- ✅ S1.9-Conversation-Model.md (300 lines)
- ✅ S1.10-Sprint-1-Acceptance-Gate.md (500 lines)
- ✅ SPRINT-1-OVERVIEW.md (this file)

**Total:** ~3,750 lines of implementation specifications + code examples

---

**Status:** ✅ Sprint 1 documentation **COMPLETE**.  
**Next:** Push to GitHub, begin implementation.  
**Timeline:** ~2 weeks (2-week sprints per plan)
