# Sprint 0 Completion - Implementation Plan

**Status:** Gap analysis and verification plan for Sprint 0 deliverables

**Target:** Ensure all 9 Sprint 0 deliverables (S0.1–S0.9) are fully implemented with passing tests.

---

## Current State Assessment

### ✅ COMPLETE
- [x] **S0.1 Monorepo Structure** — Directory layout exists, pyproject.toml configured
- [x] **Root configuration files** — Makefile, ruff.toml, mypy.ini, .pre-commit-config.yaml, .env.example, turbo.json, tsconfig.json all present
- [x] **py_core foundation modules** — tenant.py, db.py, errors.py, logging.py, otel.py, audit.py all present
- [x] **py_core tests** — test_tenant.py, test_errors.py, test_logging.py, test_fakes.py, test_audit.py, test_migrations.py present
- [x] **Alembic migrations** — env.py, 0001_baseline_mvp_schema.py, 0002_audit_hash_chain_trigger.py present
- [x] **S0.2 Docker Compose** — tools/docker-compose.yml, tools/litellm.yaml present
- [x] **S0.3 CI/CD** — .github/workflows/ci.yml present
- [x] **S0.7 Test fakes** — py_core/testing/fakes.py present
- [x] **S0.8 Golden datasets** — ml/evals/golden/intents_v0.jsonl, conversations_v0.jsonl present
- [x] **S0.8 Eval runner** — ml/evals/runner.py present
- [x] **S0.9 Acceptance tests** — tests/acceptance/ directory with conftest.py present

### ❌ GAPS FOUND

#### 1. **Missing __init__.py in key directories**
   - **Impact:** Modules not importable; tests cannot import from these packages
   - **Files to create:**
     - `services/__init__.py`
     - `apps/__init__.py`
     - `tests/__init__.py`
     - `ml/__init__.py`
     - `ml/evals/__init__.py`

#### 2. **Dependencies not installed (test failures)**
   - **Current error:** `ModuleNotFoundError: No module named 'structlog'`
   - **Impact:** Unit tests cannot run
   - **Fix:** Install uv workspace dependencies
   - **Command:** `uv sync` from root

#### 3. **Missing factories.py in py_core/testing**
   - **Expected per S0.7:** TenantFactory, CustomerFactory, ConversationFactory, MessageFactory
   - **Files to create:**
     - `packages/py_core/py_core/testing/factories.py` with pytest-factoryboy fixture definitions
   - **Required factories:**
     - TenantFactory (with tenant_id UUID)
     - CustomerFactory (with customer_id, tenant_id)
     - ConversationFactory (with conversation_id, customer_id, tenant_id)
     - MessageFactory (with message_id, conversation_id, body, timestamp)

#### 4. **Incomplete golden datasets**
   - **S0.8 requires:** intents_v0.jsonl (300 rows), entities_v0.jsonl (100 rows), rag_v0.jsonl (50 rows), guards_v0.jsonl (50 rows)
   - **Currently have:** intents_v0.jsonl (rows unknown), conversations_v0.jsonl
   - **Missing files:**
     - `ml/evals/golden/entities_v0.jsonl` (100 rows with entity extraction examples)
     - `ml/evals/golden/rag_v0.jsonl` (50 rows with retrieval test cases)
     - `ml/evals/golden/guards_v0.jsonl` (50 rows with guardrail test cases)

#### 5. **Missing conftest.py for ml/evals/tests**
   - **Expected per S0.8:** Global fixtures for eval tests
   - **File to create:** `ml/evals/tests/conftest.py` with:
     - Database fixtures (PostgreSQL via testcontainers)
     - LLM mock fixtures (using FakeLLM)
     - Golden dataset loaders
     - Pytest markers configuration

#### 6. **Missing eval test files**
   - **S0.8 requires test implementations**
   - **Files to create:**
     - `ml/evals/tests/test_eval_gates.py` — eval harness tests
     - May need additional test files for intent, entity, RAG, guardrail evals

#### 7. **Incomplete or missing acceptance test steps**
   - **S0.9 requires:** Gherkin features with BDD step definitions
   - **Expected:** tests/acceptance/features/scenarios.feature (10 Gherkin scenarios for J1–J6)
   - **Expected:** tests/acceptance/steps/steps.py (BDD step definitions)
   - **Status:** conftest.py exists, but feature files and step definitions need verification

#### 8. **Services and apps pyproject.toml may be incomplete**
   - **Files to verify/complete:**
     - `services/api/pyproject.toml`
     - `services/triage_worker/pyproject.toml`
     - `services/knowledge_worker/pyproject.toml`
     - `apps/console/package.json` (if Node-based)
     - `apps/widget/package.json` (if Node-based)
   - **Ensure:** Each has correct dependencies, workspace references, and test config

#### 9. **Verification: py_core __init__.py exports**
   - **S0.4 requires:** Public API exports in `packages/py_core/py_core/__init__.py`
   - **Should export:** TenantContext, TenantAwareSession, all error classes, logging utilities, audit functions
   - **File to review:** `packages/py_core/py_core/__init__.py`

#### 10. **Verification: Alembic configuration**
   - **File to check:** `packages/py_core/alembic/alembic.ini` — must have correct sqlalchemy.url or env-based config
   - **File to check:** `packages/py_core/alembic/env.py` — must set up SQLAlchemy logger and RLS context

---

## Implementation Plan (Ordered by Dependency)

### Phase 1: Environment & Dependencies Setup

- [ ] **1. Ensure uv workspace is configured and dependencies installed**
      Install all dependencies from root and py_core workspace
      Files: pyproject.toml (root and packages/py_core/pyproject.toml)
      Verify: `uv sync` completes without errors; `python -m pytest --collect-only` finds all tests

### Phase 2: Project Structure & Imports

- [ ] **2. Create missing __init__.py files in package directories**
      Create empty or minimal __init__.py to make directories importable Python packages
      Files:
        - services/__init__.py
        - apps/__init__.py
        - tests/__init__.py
        - ml/__init__.py
        - ml/evals/__init__.py
        - ml/evals/tests/__init__.py
      Verify: `python -c "import services; import apps; import ml; import ml.evals"` succeeds without errors

- [ ] **3. Verify py_core __init__.py exports all public API**
      Review packages/py_core/py_core/__init__.py and ensure it exports:
        - MissingTenantContextError, set_tenant, get_tenant, clear_tenant
        - TenantAwareSession, get_db_session
        - All error classes from errors.py
        - logging setup and PII redaction utilities
        - audit functions and hash chain verification
      Files: packages/py_core/py_core/__init__.py
      Verify: `python -c "from py_core import set_tenant, get_tenant, TenantAwareSession"` succeeds

### Phase 3: Test Fixtures & Factories

- [ ] **4. Create factories.py with pytest-factoryboy fixtures**
      Implement factory classes and pytest fixtures for:
        - TenantFactory (generates valid UUID tenant_id)
        - CustomerFactory (customer_id, tenant_id, email, name)
        - ConversationFactory (conversation_id, customer_id, tenant_id, subject)
        - MessageFactory (message_id, conversation_id, body, sender, timestamp)
      Files: packages/py_core/py_core/testing/factories.py
      Verify: `python -c "from py_core.testing import TenantFactory, CustomerFactory"` and `pytest packages/py_core/tests/ -m unit --collect-only` shows factory fixtures

- [ ] **5. Create conftest.py for ml/evals/tests**
      Set up global pytest configuration and fixtures:
        - Database fixture (testcontainers PostgreSQL or in-memory)
        - LLM mock fixture (FakeLLM from py_core)
        - Golden dataset loaders (load intents, entities, RAG, guards)
        - Pytest markers: @pytest.mark.eval, @pytest.mark.smoke
      Files: ml/evals/tests/conftest.py
      Verify: `pytest ml/evals/tests/ --collect-only` shows fixtures and markers available

### Phase 4: Golden Datasets

- [ ] **6. Generate missing golden dataset files**
      Create three additional golden datasets per S0.8 spec:
      Files:
        - ml/evals/golden/entities_v0.jsonl (100 rows, each with entity extraction test case)
        - ml/evals/golden/rag_v0.jsonl (50 rows, each with retrieval/relevance test case)
        - ml/evals/golden/guards_v0.jsonl (50 rows, each with guardrail/safety test case)
      Format: JSONL, one test case per line, fields: id, input, expected_output, metadata
      Verify: 
        - `wc -l ml/evals/golden/entities_v0.jsonl` shows >= 100 lines
        - `wc -l ml/evals/golden/rag_v0.jsonl` shows >= 50 lines
        - `wc -l ml/evals/golden/guards_v0.jsonl` shows >= 50 lines
        - `python -c "import jsonlines; list(jsonlines.open('ml/evals/golden/entities_v0.jsonl'))"` parses without error

### Phase 5: Eval Tests

- [ ] **7. Create eval test file: test_eval_gates.py**
      Implement core eval tests per S0.8:
      Files: ml/evals/tests/test_eval_gates.py
      Content:
        - test_intent_classification_eval (runs intents_v0.jsonl through classifier)
        - test_entity_extraction_eval (runs entities_v0.jsonl through entity extractor)
        - test_rag_retrieval_eval (runs rag_v0.jsonl through retrieval pipeline)
        - test_guardrail_eval (runs guards_v0.jsonl through guardrail checker)
      Verify: `pytest ml/evals/tests/test_eval_gates.py -m eval -v` runs without errors (tests may fail if LLM logic incomplete, but test structure is valid)

### Phase 6: Acceptance Tests

- [ ] **8. Verify/complete Gherkin feature file**
      Ensure tests/acceptance/features/scenarios.feature exists with 10 scenarios:
        - J1: Autonomous WISMO (What Is Status Of My...)
        - J2: Proactive Notifications
        - J3: Escalation Path
        - J4: Knowledge Base Query
        - J5: Sentiment-Driven Follow-up
        - J6: Account Health Check
        - Technical scenarios: Error handling, RLS enforcement, Audit trail
      Files: tests/acceptance/features/scenarios.feature
      Verify: `pytest tests/acceptance/ --collect-only -m bdd` lists all scenarios

- [ ] **9. Implement BDD step definitions**
      Create tests/acceptance/steps/steps.py with pytest-bdd step implementations:
        - @given("a tenant {tenant_name}") — create test tenant
        - @when("I send a message...") — call API or service
        - @then("the conversation is stored...") — verify database state
        - Steps for all J1–J6 scenarios
      Files: tests/acceptance/steps/steps.py
      Verify: `pytest tests/acceptance/ -m bdd -v` collects and can run step definitions

### Phase 7: Core Tests Verification

- [ ] **10. Run all py_core unit tests to verify they pass**
      Ensure all unit tests in packages/py_core/tests/ pass with fixtures and factories in place
      Files: packages/py_core/tests/test_*.py
      Verify: 
        - `pytest packages/py_core/tests/ -m unit -v` — all pass
        - `pytest packages/py_core/tests/ --cov=packages/py_core --cov-report=term-missing` — coverage > 80%

- [ ] **11. Run migration tests to verify database schema**
      Ensure Alembic migrations create all 18 required tables and triggers work correctly
      Files: packages/py_core/tests/test_migrations.py
      Verify: 
        - `pytest packages/py_core/tests/test_migrations.py -m integration -v` — all pass
        - Database has all 18 tables with RLS policies applied
        - Audit hash chain triggers execute without error

### Phase 8: Integration & Full Pipeline Verification

- [ ] **12. Run full test suite (unit + integration + eval smoke)**
      Execute complete verification across all layers
      Verify:
        - `pytest packages/py_core/tests/ -m unit` (< 3 min)
        - `pytest packages/py_core/tests/ -m integration` (< 10 min, may need Docker)
        - `pytest ml/evals/tests/ -m eval -k "smoke"` (< 15 min)
        - `make smoke` — lint + typecheck pass
        - `make lint` — ruff check passes
        - `make typecheck` — mypy --strict passes for py_core

### Phase 9: Services & Apps Bootstrap

- [ ] **13. Verify services and apps pyproject.toml files**
      Ensure each service/app has complete, workspace-aware pyproject.toml:
      Files:
        - services/api/pyproject.toml — depends on py_core, has FastAPI
        - services/triage_worker/pyproject.toml — depends on py_core, has LangGraph
        - services/knowledge_worker/pyproject.toml — depends on py_core, has RAG libs
        - apps/console/package.json (or pyproject.toml if Python)
        - apps/widget/package.json (or pyproject.toml if TypeScript/JS)
      Verify: `uv sync` completes; each service can import from py_core

### Phase 10: Cleanup & Finalization

- [ ] **14. Delete Sprint 0 spec files (after all tests pass)**
      Remove documentation files per the S0 cleanup list
      Files to delete:
        - S0.1-Monorepo-Structure.md
        - S0.2-Local-Development-Stack.md
        - S0.3-CI-CD-Pipeline.md
        - S0.4-py_core-Foundation.md
        - S0.5-PostgreSQL-Schema-and-Migrations.md
        - S0.6-Audit-Hash-Chain.md
        - S0.7-Test-Kit-Fakes-and-Fixtures.md
        - S0.8-Eval-Harness-and-Golden-Datasets.md
        - S0.9-MVP-Acceptance-Scenarios.md
        - SPRINT-0-SUMMARY.md
        - README-IMPLEMENTATION-PLAN.md
      Verify: Root directory no longer contains S0.* or SPRINT-0-* files

- [ ] **15. Create final Sprint 0 verification report**
      Document that all 9 deliverables are implemented and tested
      Files: Create `.agents/tasks/sprint0-verification.md` with:
        - All test results (unit, integration, acceptance, eval)
        - Test coverage report
        - Lint and type check results
        - Deployment readiness checklist
      Verify: All success criteria met; ready for Sprint 1

---

## Success Criteria

✅ **All 9 Sprint 0 deliverables fully implemented**
- S0.1: Monorepo structure complete with all configs
- S0.2: Docker Compose with all 7 services running
- S0.3: CI/CD pipeline complete and passing
- S0.4: py_core foundation fully functional
- S0.5: PostgreSQL schema with 18 tables and RLS working
- S0.6: Audit hash chain verifying tamper detection
- S0.7: Test fakes passing contract tests
- S0.8: Eval harness and golden datasets complete
- S0.9: BDD acceptance scenarios passing

✅ **All tests passing**
- Unit tests: `pytest packages/py_core/tests/ -m unit` — all pass
- Integration tests: `pytest packages/py_core/tests/ -m integration` — all pass
- Eval tests: `pytest ml/evals/tests/ -m eval` — all pass
- Acceptance tests: `pytest tests/acceptance/ -m bdd` — all pass
- Lint: `ruff check packages/` — no errors
- Type: `mypy packages/py_core --strict` — no errors

✅ **Local development ready**
- `make up` — Docker stack starts without errors
- `make smoke` — Lint + basic import checks pass
- `make test` — All unit tests pass < 3 minutes
- All dependencies installed via `uv sync`

---

## Notes

- **Dependency Management:** Use `uv sync` to install all workspace dependencies. The root pyproject.toml declares py_core as a workspace member, which enables local imports.
- **Test Markers:** All tests are marked with @pytest.mark (unit, integration, eval). Use `-m` flag to run specific tiers.
- **Database Fixtures:** Integration tests may require testcontainers PostgreSQL. Ensure Docker is running or use in-memory SQLite for lighter testing.
- **Alembic Configuration:** Migrations reference DATABASE_URL environment variable. Ensure .env.local is configured before running migrations.
- **Acceptance Tests:** BDD tests (@pytest-bdd) are initially @pending. Implement steps incrementally as Sprint 1 APIs become available.

---

## Next Steps After Sprint 0 Completion

Once all gaps are filled and tests pass:

1. **Push to GitHub:** Commit implementation, create PR, merge after CI passes
2. **Sprint 1 Kickoff:** Begin S1.1 (Message Normalization) with full infrastructure in place
3. **Cleanup:** Delete S0.* documentation files once specs are locked in code

---

**Plan Created:** 2026-10-10  
**Target Completion:** Immediate (gap-filling)  
**Estimated Effort:** 2-4 hours (depending on whether Docker/testcontainers need setup)
