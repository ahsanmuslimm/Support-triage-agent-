# Triage Agent - Implementation Documentation

## 📚 Complete Implementation Plan for MVP

This folder contains comprehensive documentation for building the **Triage Agent** — an AI-powered customer support triage platform following the implementation plan from the specification documents.

---

## 📖 Core Specification Documents

Start here for the full context:

1. **[Solution Proposal](./Docs/ai-powered-customer-support-triage-agent-solution-proposal.md)**
   - Problem statement, market opportunity, ROI
   - Core capabilities and value proposition
   - Commercial model

2. **[Product & Technical Specification](./Docs/triage-agent-product-and-technical-specification.md)**
   - Product requirements (PR-ING-01 through FR-DEV-04)
   - Architecture (C4 levels 1-3)
   - Complete schema (PostgreSQL DDL)
   - API surface (REST, webhooks)

3. **[Implementation Plan](./Docs/implementation-plan.md)**
   - 3-stage delivery roadmap (MVP → GA → Commercial)
   - Sprint breakdown with deliverables
   - Optimized TDD approach
   - Test pyramid and gates

---

## 🚀 Sprint 0 - Foundation & Test Harness

Complete implementation documentation for all 9 deliverables:

### Documentation Files (Read in Order)

| Sprint Item | File | What's In It |
|---|---|---|
| **S0.1** | [Monorepo Structure](./S0.1-Monorepo-Structure.md) | Project layout, uv/Turborepo config, Makefile |
| **S0.2** | [Local Dev Stack](./S0.2-Local-Development-Stack.md) | Docker Compose, 7 services, health checks |
| **S0.3** | [CI/CD Pipeline](./S0.3-CI-CD-Pipeline.md) | GitHub Actions workflows, security scans |
| **S0.4** | [py_core Foundation](./S0.4-py_core-Foundation.md) | Tenant context, DB session, errors, logging |
| **S0.5** | [PostgreSQL Schema](./S0.5-PostgreSQL-Schema-and-Migrations.md) | 18 tables, RLS policies, Alembic migrations |
| **S0.6** | [Audit Hash Chain](./S0.6-Audit-Hash-Chain.md) | Tamper detection, hash verification |
| **S0.7** | [Test Kit Fakes](./S0.7-Test-Kit-Fakes-and-Fixtures.md) | FakeLLM, FakeClock, FakeShopify, FakeStripe |
| **S0.8** | [Eval Harness](./S0.8-Eval-Harness-and-Golden-Datasets.md) | Golden datasets, eval runner, metrics |
| **S0.9** | [BDD Scenarios](./S0.9-MVP-Acceptance-Scenarios.md) | Gherkin features for 10 journeys |

### Quick Summary

[**Sprint 0 Summary**](./SPRINT-0-SUMMARY.md) — 2-page overview with architecture decisions, file structure, and key commands.

---

## 🎯 How to Use This Documentation

### For Implementation Teams
1. Read the specification documents in order (top to bottom)
2. Review Sprint 0 summary for context
3. Deep-dive into each S0.X file for detailed implementation
4. Each file includes:
   - Objective
   - Code/config to create
   - Tests to verify
   - Deliverables checklist
   - Definition of Done

### For Architects
- Focus on Specification sections 0–13 (architecture decisions)
- Review S0.1 (monorepo structure) and S0.5 (schema)
- Check S0.6 (audit) and S0.4 (tenancy) for security

### For Test Engineers
- Start with S0.7 (test kit fakes)
- Review S0.8 (eval harness and golden datasets)
- Check S0.9 (acceptance scenarios)
- See S0.3 (CI/CD pipeline) for test orchestration

### For DevOps
- S0.2 (Docker Compose local stack)
- S0.3 (GitHub Actions workflows)
- Specification §27 (Infrastructure)

---

## 🔑 Key Architectural Decisions

These are locked in from Sprint 0 and cannot be changed later:

| Decision | Implementation Details | Reference |
|---|---|---|
| **Tenant Isolation** | Composite keys (tenant_id, id) + PostgreSQL RLS on every table | S0.5 (schema) |
| **Deterministic Agent** | LangGraph state graph (not free-form agent) | Spec §17 |
| **Two-Stage Classification** | k-NN (30 ms) → Haiku (only low-confidence) | Spec §17.3 |
| **Append-Only Audit** | SHA256 hash chain, triggers prevent UPDATE/DELETE | S0.6 (audit) |
| **Event Durability** | Transactional outbox in Postgres (Kafka comes in Stage 2) | Spec §23.2 |
| **PII Pseudonymization** | Before any LLM call, vault stores mappings | S0.4 (logging) |
| **Strict Type Safety** | mypy --strict, TypeScript strict, Ruff linting | S0.1 (monorepo) |

---

## 📊 Implementation Status

### Sprint 0 Status
- **Phase 1: Planning** ✅ Complete
  - Architecture design
  - Tech stack selection
  - Schema design
  - Test strategy

- **Phase 2: Documentation** ✅ Complete (This folder)
  - All 9 deliverables documented
  - Code examples provided
  - Tests defined
  - Deployment instructions

- **Phase 3: Implementation** 🔄 Ready to begin
  - Generate project structure from S0.1
  - Create services from S0.2
  - Set up CI from S0.3
  - Build py_core from S0.4
  - Run migrations from S0.5
  - etc.

---

## 🛠️ Common Commands

### Setup
```bash
# Clone and enter directory
cd Support-triage-agent-

# Copy environment
cp .env.example .env.local

# Install dependencies
make setup

# Start local services
make up

# Run all tests
make test

# Check health
make smoke
```

### Development
```bash
# Lint and type check
make lint
make typecheck

# Run specific test suite
pytest tests/unit -v
pytest tests/integration -v
pytest tests/acceptance -v

# Database
make db-migrate
make db-rollback

# Stop services
make down
```

### CI/CD
```bash
# Runs automatically on push/PR
# Check status at: https://github.com/[org]/Support-triage-agent-/actions
```

---

## 📋 Files in This Repository

### Specification (Read First)
- `Docs/ai-powered-customer-support-triage-agent-solution-proposal.md` — Proposal
- `Docs/triage-agent-product-and-technical-specification.md` — Spec
- `Docs/implementation-plan.md` — Delivery roadmap

### Sprint 0 Documentation (Detailed Implementation)
- `S0.1-Monorepo-Structure.md` — Project setup
- `S0.2-Local-Development-Stack.md` — Docker services
- `S0.3-CI-CD-Pipeline.md` — CI/CD
- `S0.4-py_core-Foundation.md` — Shared library
- `S0.5-PostgreSQL-Schema-and-Migrations.md` — Database
- `S0.6-Audit-Hash-Chain.md` — Audit logging
- `S0.7-Test-Kit-Fakes-and-Fixtures.md` — Test doubles
- `S0.8-Eval-Harness-and-Golden-Datasets.md` — AI evaluation
- `S0.9-MVP-Acceptance-Scenarios.md` — BDD tests

### Summaries
- `SPRINT-0-SUMMARY.md` — Quick reference (2 pages)
- `README-IMPLEMENTATION-PLAN.md` — This file

---

## ✅ Definition of Ready

Before starting implementation, confirm:

- [ ] All team members have read the Specification documents
- [ ] Architecture decisions are understood and agreed upon
- [ ] S0.1–S0.9 files have been reviewed for their domains
- [ ] Local setup has been tested (or understood for DevOps)
- [ ] CI/CD pipeline architecture is approved

---

## ❓ FAQ

**Q: Where do I start?**  
A: Read the Specification documents first (Solution Proposal → Technical Spec → Implementation Plan). Then review SPRINT-0-SUMMARY.md for context.

**Q: How detailed are these docs?**  
A: Every S0.X file includes complete code/config, tests, and a Definition of Done. They're implementation-ready—just copy and adapt.

**Q: What if I want to change the architecture?**  
A: Review the architectural decisions in §0.3 of the Implementation Plan. Major changes (e.g., different database, agent runtime, tenancy model) require re-evaluation of all MVP items.

**Q: Can I skip Sprint 0?**  
A: No. Sprint 0 builds the foundation that all future sprints depend on. Shortcuts here multiply technical debt later.

**Q: When do real features start?**  
A: Sprint 1 (Ingestion & Conversation Core) begins after Sprint 0 is complete and all tests pass.

---

## 📞 Key Contacts & Roles

| Role | Responsibility |
|---|---|
| **Product Owner** | Requirements, release gates, MVP success criteria |
| **Technical Lead** | Architecture decisions, code review, quality gates |
| **Backend Lead** | py_core, database, API implementation |
| **Frontend Lead** | Widget, console UI, acceptance tests |
| **DevOps Lead** | CI/CD, infrastructure, local development setup |
| **QA Lead** | Test strategy, acceptance criteria, gate verification |

---

## 📈 Next Steps After Sprint 0

1. **Sprint 1 – Ingestion & Conversation Core** (2 weeks)
   - Message normalization
   - Zendesk webhooks
   - Idempotency + coalescing
   - Cryptography (envelope + PII vault)
   - First acceptance scenario (J1) passes

2. **Sprint 2 – Triage Graph & Classification** (2 weeks)
   - LangGraph topology (15 nodes)
   - Two-stage intent classifier
   - Safety screen + injection detection
   - More scenarios pass (J1, J2, J3)

3. **Sprint 3 – Knowledge & Guardrails** (2 weeks)
   - KB ingestion (Zendesk, file upload, website)
   - RAG pipeline (retrieval + rerank + citations)
   - Output guards (groundedness, PII, promises)

4. ... and so on through Sprint 5 (MVP Gate)

---

## 📝 Document Version

- **Version:** 1.0 (Sprint 0 Complete)
- **Date:** October 2026
- **Owner:** Muhammad Ahsan
- **Status:** Ready for Implementation

---

## 🔗 References

- LangGraph: https://langchain-ai.github.io/langgraph/
- pytest-bdd: https://pytest-bdd.readthedocs.io/
- SQLAlchemy + pgvector: https://python.langchain.com/docs/integrations/vectorstores/pgvector/
- RFC 9457 (Problem Details): https://www.rfc-editor.org/rfc/rfc9457
- Alembic: https://alembic.sqlalchemy.org/

---

**Ready to build.** Follow the Sprint 0 docs in order, run the tests, and push to main. 🚀
