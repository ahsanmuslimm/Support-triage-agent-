# Sprint 0 - Foundation & Test Harness - Complete Documentation

## Overview
Sprint 0 establishes the complete foundational infrastructure for the Triage Agent MVP. All 9 deliverables are documented with code, configuration, tests, and deployment instructions.

## All Sprint 0 Deliverables

### 📋 Documentation Files Created

| # | Deliverable | File | Focus |
|---|---|---|---|
| **0.1** | Monorepo Structure | `S0.1-Monorepo-Structure.md` | uv workspaces, Turborepo, linting, typing, pre-commit |
| **0.2** | Local Dev Stack | `S0.2-Local-Development-Stack.md` | Docker Compose (Postgres, Redis, MinIO, Langfuse, LiteLLM) |
| **0.3** | CI/CD Pipeline | `S0.3-CI-CD-Pipeline.md` | GitHub Actions (lint → unit → integration → security → eval) |
| **0.4** | py_core Foundation | `S0.4-py_core-Foundation.md` | Tenant context, DB session, errors (RFC 9457), logging |
| **0.5** | PostgreSQL Schema | `S0.5-PostgreSQL-Schema-and-Migrations.md` | 18 tables with RLS, Alembic migrations |
| **0.6** | Audit Hash Chain | `S0.6-Audit-Hash-Chain.md` | Tamper-evident append-only log with SHA256 chain |
| **0.7** | Test Kit Fakes | `S0.7-Test-Kit-Fakes-and-Fixtures.md` | FakeLLM, FakeClock, FakeEventBus, FakeShopify, FakeStripe |
| **0.8** | Eval Harness | `S0.8-Eval-Harness-and-Golden-Datasets.md` | Golden datasets (intents, entities, RAG, guards) |
| **0.9** | BDD Scenarios | `S0.9-MVP-Acceptance-Scenarios.md` | Gherkin features for 6 journeys (J1–J6) |

---

## Quick Reference

### Architecture Decision Log

| Decision | Choice | Why |
|---|---|---|
| **Monorepo** | uv + Turborepo | Fast, lightweight, easy to split later |
| **Database** | PostgreSQL 18 + pgvector | One transactional store, native RLS |
| **Agent Runtime** | LangGraph deterministic graph | Auditable, resumable, bounded behavior |
| **Classification** | Two-stage (k-NN → Haiku) | 30 ms + LLM on low-confidence only |
| **Tenancy** | Composite keys + RLS | Enforced at DB level, not app level |
| **Audit** | Hash-chained append-only | Tamper detection, immutability |
| **LLM Access** | LiteLLM gateway | Vendor-agnostic, fallbacks, budgets |
| **Testing** | Optimized TDD (5 tiers) | Strict on domain, eval-driven on LLM, smoke on UI |

---

## File Structure After Sprint 0

```
Support-triage-agent-/
├── py_core/                              # Shared Python library
│   ├── src/triage/
│   │   ├── core/
│   │   │   ├── tenant.py                 # Tenant context (mandatory)
│   │   │   ├── db.py                     # DB session + RLS
│   │   │   ├── errors.py                 # RFC 9457 errors
│   │   │   └── logging.py                # Structured logging + PII redaction
│   │   ├── audit/
│   │   │   ├── hash_chain.py             # Hash chain verification
│   │   │   └── log.py                    # Audit logging
│   │   ├── test_kit/
│   │   │   ├── fake_llm.py               # LLM mock
│   │   │   ├── fake_clock.py             # Deterministic time
│   │   │   ├── fake_event_bus.py         # Event ordering
│   │   │   ├── fake_shopify.py           # Shopify mock
│   │   │   └── fake_stripe.py            # Stripe mock
│   │   └── models/
│   │       └── __init__.py               # Shared Pydantic models
│   ├── tests/
│   │   ├── test_tenant.py                # Tenant context tests
│   │   ├── test_errors.py                # Error model tests
│   │   ├── test_audit_chain.py           # Hash chain tests
│   │   ├── test_audit_logger.py          # Audit logging tests
│   │   ├── test_schema_rls.py            # RLS enforcement tests
│   │   └── test_fakes.py                 # Fake contract tests
│   └── pyproject.toml                    # py_core config (mypy --strict)
│
├── alembic/                              # Database migrations
│   ├── env.py
│   ├── versions/
│   │   ├── 001_initial_schema.py         # 18 tables + RLS
│   │   └── 002_audit_hash_chain.py       # Hash chain triggers
│   └── alembic.ini
│
├── ml/                                   # ML components
│   ├── golden/                           # Golden datasets
│   │   ├── intents.jsonl                 # 300 rows
│   │   ├── entities.jsonl                # 100 rows
│   │   ├── rag.jsonl                     # 50 rows
│   │   └── guards.jsonl                  # 50 rows
│   └── evals/
│       ├── eval_runner.py                # Eval harness
│       └── README.md
│
├── tests/
│   ├── evals/
│   │   ├── test_intent_classifier_eval.py
│   │   └── conftest.py
│   ├── acceptance/
│   │   ├── features/
│   │   │   └── scenarios.feature         # 10 Gherkin scenarios (J1–J6)
│   │   ├── steps/
│   │   │   └── steps.py                  # BDD step definitions
│   │   └── conftest.py                   # Fixtures
│   ├── conftest.py                       # Global fixtures (fakes)
│   └── pytest.ini                        # Pytest config
│
├── infra/
│   ├── docker-compose.yml                # 7 services (Postgres, Redis, etc.)
│   ├── init-postgres.sql                 # pgvector setup
│   ├── litellm-config.yaml               # LLM gateway config
│   └── health-check.sh
│
├── .github/workflows/
│   ├── ci.yml                            # Main CI pipeline
│   ├── nightly.yml                       # Full evals + mutation tests
│   └── performance.yml                   # Benchmarks
│
├── Makefile                              # Common commands
├── pyproject.toml                        # Root uv workspace
├── tsconfig.json                         # TypeScript config
├── turbo.json                            # Turborepo config
├── .pre-commit-config.yaml               # Pre-commit hooks
├── ruff.toml                             # Ruff linter config
├── .env.example                          # Safe environment template
└── README.md
```

---

## Development Workflow

### Local Setup
```bash
# 1. Copy environment
cp .env.example .env.local

# 2. Install dependencies
make setup

# 3. Start services
make up

# 4. Run tests
make test

# 5. Verify health
make smoke
```

### Daily Development
```bash
# Make changes to code
# ...

# Run tests locally (< 3 min)
make test

# Lint and type check
make lint
make typecheck

# Push to branch
git add .
git commit -m "feat: implement X"
git push -u origin feature/X

# CI runs automatically (GitHub Actions)
# PRs required to pass:
# - Lint & type check
# - Unit tests
# - Integration tests
# - Security scans
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "add X column"

# Run migrations
make db-migrate

# Rollback last migration
make db-rollback
```

---

## Testing Strategy (Optimized TDD)

### Test Pyramid
- **70% Unit tests** (< 3 min) — Domain logic, fakes
- **20% Integration tests** (< 10 min) — Real services (Testcontainers)
- **10% E2E / Acceptance** (< 15 min) — Full journeys

### Test Markers
```bash
pytest tests/ -m unit         # Unit tests only
pytest tests/ -m integration  # Integration tests
pytest tests/ -m eval         # Eval tests (slow)
pytest tests/ -m smoke        # Quick health checks
```

### Running Specific Tests
```bash
# Run tests matching a pattern
pytest tests/ -k "test_tenant"

# Run with coverage
pytest tests/ --cov=py_core --cov-report=html

# Run in parallel
pytest tests/ -n auto
```

---

## Key Files & Their Purposes

### Core Library (`py_core/`)
- **`tenant.py`** — Enforce mandatory tenant context; fail-closed without context
- **`db.py`** — TenantAwareSession wraps RLS enforcement
- **`errors.py`** — RFC 9457 error responses for API contracts
- **`logging.py`** — PII redaction, structured JSON logging, OTel instrumentation

### Database
- **`001_initial_schema.py`** — 18 tables with RLS policies
- **`002_audit_hash_chain.py`** — Hash chain triggers for tamper detection

### Testing
- **`test_kit/`** — Fakes that pass contract tests (FakeLLM, FakeShopify, etc.)
- **`golden/`** — Golden datasets for eval-driven development (300 intents, 100 entities, etc.)
- **`acceptance/`** — Gherkin scenarios (10 journeys, @pending initially)

### Infrastructure
- **`docker-compose.yml`** — All dev services (Postgres, Redis, MinIO, Langfuse, LiteLLM)
- **`.github/workflows/`** — Multi-stage CI (lint → unit → integration → security)

---

## Success Criteria for Sprint 0

✓ **All 9 deliverables documented** with code, config, and tests  
✓ **Local stack works** — `make up && make smoke` < 30s  
✓ **All tests pass** — Unit (< 3 min), Integration (< 10 min), Security scans  
✓ **RLS working** — Tenant A cannot read/write tenant B data  
✓ **Audit chain verified** — Tampering detected via hash chain  
✓ **Fakes pass contract tests** — Ready for adapter swaps  
✓ **Acceptance scenarios written** — 10 @pending Gherkin features  
✓ **CI green** — All workflows pass on empty repo  

---

## What's Next (Sprint 1)

**Sprint 1 – Ingestion & Conversation Core** (2 weeks)

- Message ingestion (email, web chat)
- Zendesk webhook receiver
- Idempotency enforcement
- Message coalescing (debounce)
- Identity resolution
- Encryption (envelope + pseudonymization)
- Outbox writer for event durability

**First acceptance scenario to pass:** J1 (Autonomous WISMO) reaches end-to-end

---

## Documentation Index

All Sprint 0 files:
- `S0.1-Monorepo-Structure.md` — Project setup
- `S0.2-Local-Development-Stack.md` — Docker services
- `S0.3-CI-CD-Pipeline.md` — Continuous integration
- `S0.4-py_core-Foundation.md` — Shared library
- `S0.5-PostgreSQL-Schema-and-Migrations.md` — Database
- `S0.6-Audit-Hash-Chain.md` — Audit logging
- `S0.7-Test-Kit-Fakes-and-Fixtures.md` — Test doubles
- `S0.8-Eval-Harness-and-Golden-Datasets.md` — AI evaluation
- `S0.9-MVP-Acceptance-Scenarios.md` — BDD tests

---

**Sprint 0 Complete** ✅  
**Ready for implementation** 🚀

Status: Foundation established, all infrastructure documented, ready for feature development in Sprint 1.
