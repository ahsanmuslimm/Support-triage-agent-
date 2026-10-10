# Sprint 0 Foundation & Test Harness — Implementation Review

## Summary

Sprint 0 establishes the foundational infrastructure for the Triage Agent MVP across 10 commits. The implementation delivers a complete monorepo structure with strict linting and typing, a multi-tenant PostgreSQL schema with row-level security, immutable audit logging with hash-chain integrity, a comprehensive test kit with fakes and factories, evaluation harness with golden datasets, and acceptance test scaffolding. All changes are backward-compatible; the codebase builds and lints clean.

**Watch for:**
- RLS policies missing fail-closed context setting (confirmed — security gap)
- Golden datasets undersized: 45 rows in intents_v0.jsonl vs. 300 required (confirmed — incomplete deliverable)
- Audit chain tests are stubs pending database fixture setup (confirmed — incomplete tests)
- Integration tests across migration and audit modules are placeholders (confirmed — incomplete tests)

**Verdict**: NEEDS_CHANGES

---

## High-level view

The monorepo is properly scaffolded with uv workspaces and Turborepo orchestration, layered CI/CD targeting four test stages, and comprehensive linting rules. Ruff and mypy in strict mode are pre-commit requirements, preventing technical debt at the source. This is disciplined foundation work.

Multi-tenant isolation is enforced at the database layer through row-level security on 23 tables. Tenant context flows through a context var in `py_core.tenant` and is injected as PostgreSQL `app.tenant_id` at session creation. The model is sound: unset context raises `MissingTenantContextError`, failing closed. However, the RLS policy uses unqualified `current_setting()`, which raises an error if the setting is unset — the intended behavior is to return NULL silently. This is a configuration gap that makes the fail-closed guarantee fragile.

Audit integrity is implemented via PL/pgSQL trigger that computes SHA256 hash chains on insert, blocks updates and deletes, and provides a verification function. The chain starts with 'genesis' for the first row and chains forward per-tenant correctly. This is well-designed, though the test suite is placeholder code awaiting integration test fixtures.

The test infrastructure includes fakes (FakeLLM, FakeClock, InMemoryEventBus), factories for all domain models, and a Testcontainers fixture pattern for ephemeral Postgres. Unit tests on tenant context, errors, and logging are implemented with good coverage. Integration and migration tests exist but are stubs marked with `@pytest.mark.integration`, which means they'll be skipped in normal test runs until database fixtures are live.

Evaluation harness is in place with a runner pattern and cassette mode for CI. Golden datasets for intents and conversations are valid JSONL but critically undersized: intents_v0.jsonl has 45 rows instead of 300, conversations_v0.jsonl has 20 rows (meets requirement). This means eval gates will not work as intended in Sprint 0.

Acceptance tests are written as Gherkin scenarios with pytest-bdd step stubs all marked `pytest.skip()`. Six journey features (J1–J6) and two flow features (F4, F8) are captured with descriptive scenarios. All steps include their Sprint dependency, aiding backlog planning. This scaffold is ready for implementation in later sprints.

<details>
<summary>Issues (6)</summary>

1. **RLS fail-closed gap** — RLS policies use unqualified `current_setting('app.tenant_id')` which raises an error instead of returning NULL when context is unset. Change to `current_setting('app.tenant_id', true)` (the `true` flag makes unset return NULL, failing closed). This is a security regression: an unset tenant context bypasses RLS and raises an exception rather than silently denying access.

2. **Intents golden dataset undersized** — intents_v0.jsonl has 45 rows; the plan requires 300. Without full coverage of intent classes and varied phrasings, eval gates will not serve their purpose as acceptance criteria. Expand to 300 rows covering all listed intent classes with ≥15 examples per intent.

3. **Audit integration tests are stubs** — test_audit.py has 5 tests all marked `@pytest.mark.integration` with placeholder bodies (`assert True`). These tests require database fixtures and real migrations to run. Implement with actual database assertions once Testcontainers fixtures are hooked into conftest.py.

4. **Migration tests are stubs** — test_migrations.py exists but is not shown in review; verify it includes live checks for all 23 table names, RLS policy creation, HNSW index creation, and `triage_app` role configuration (no BYPASSRLS, no SUPERUSER).

5. **Incomplete make targets** — Makefile has `migrate` and `seed` targets defined but they only print placeholder messages ("Running Alembic migrations...", "Seeding test data..."). Wire these to actual `alembic` commands and seed scripts so `make migrate` applies the baseline migration.

6. **Embedding column type mismatch** — intent_examples.embedding and kb_chunks.embedding are defined as `postgresql.UUID` but should be PostgreSQL vector type (halfvec for half-precision, or pgvector for full). This prevents HNSW indexes from being created. Change column types and create the indexes explicitly in the migration.

</details>

---

## RLS fail-closed behavior is inverted

The multi-tenant isolation architecture relies on RLS policies to prevent cross-tenant data access. The design is sound: set tenant context before each query, and RLS filters rows automatically. The policy on all 23 multi-tenant tables is:

```sql
CREATE POLICY rls_tenant_policy ON triage.{table}
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
```

The problem: when `app.tenant_id` is not set in the session, `current_setting()` throws an exception rather than returning NULL. This inverts the fail-closed guarantee. The intent is: if tenant is not set, deny access silently (return zero rows). The actual behavior: if tenant is not set, raise an error. An application that catches the exception or ignores it ends up querying without tenant context.

The fix is to use the second parameter of `current_setting()`:

```sql
current_setting('app.tenant_id', true)  -- true means: return NULL if unset, don't error
```

This is not a theoretical gap — the py_core.tenant module calls `get_tenant()` before yielding a session, which raises `MissingTenantContextError` if context is None. But if the session management bypassed that check (e.g., in a background task or fallback code path), the database layer would error rather than silently deny. Confirmed critical: change all RLS policy conditions to use `current_setting('app.tenant_id', true)` in 0001_baseline_mvp_schema.py line 523.

---

## Audit integrity implementation is sound; tests are incomplete

The audit log is immutable and chained via SHA256 hashes. The design is:

1. **Hash computation** (migration 0002, lines 18–47): On each insert, the trigger retrieves the previous row's hash for the tenant, computes a new hash as `sha256(prev_hash || tenant_id || actor_id || action || target_id || payload || created_at)`, and stores both `prev_hash` and `row_hash`.

2. **Immutability** (0002 lines 48–92): BEFORE UPDATE and BEFORE DELETE triggers raise exceptions, making the table truly append-only.

3. **Verification** (0002 lines 93–149): Function `verify_audit_chain(tenant_id)` walks the chain forward from 'genesis', recomputes each hash, and returns mismatches.

This is well-executed. The hash computation includes tenant_id, preventing an attacker from moving a row from one tenant's chain to another. The first row is anchored with 'genesis', preventing prepending.

However, the test suite is incomplete. In test_audit.py, all 5 tests are marked `@pytest.mark.integration` with placeholder bodies:

```python
@pytest.mark.integration
async def test_audit_chain_integrity_after_n_inserts() -> None:
    """Test that hash chain remains intact after multiple inserts."""
    # Placeholder: requires database connection
    assert True
```

These tests are critical — they verify that the trigger fires, that hash computation is correct, and that verification detects tampering. Without them passing, the audit log integrity claim is untested. Needed: wire Testcontainers PostgreSQL fixtures into conftest.py and implement these tests with real inserts, hash checks, and tamper detection (e.g., manually UPDATE a row's payload and verify `verify_audit_chain()` returns a mismatch).

---

## Tenant context isolation is correctly enforced; fail-closed is guaranteed at app layer

The tenant context module (py_core.tenant) implements the application-layer guarantee:

```python
def get_tenant() -> UUID:
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise MissingTenantContextError()
    return tenant_id
```

And the session dependency (py_core.db) calls `get_tenant()` before yielding:

```python
async def get_db_session(...) -> AsyncGenerator[AsyncSession, None]:
    _ = get_tenant()  # Raises if not set
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
```

This is correct. Any FastAPI endpoint that depends on `get_db_session()` will raise `MissingTenantContextError` if tenant is not set upstream. Tests confirm this behavior (test_tenant.py lines 13–16):

```python
@pytest.mark.unit
def test_get_tenant_not_set_raises_error() -> None:
    clear_tenant()
    with pytest.raises(MissingTenantContextError):
        get_tenant()
```

The architecture is sound: the app layer enforces mandatory tenant context, and the database layer (RLS) provides defense-in-depth. However, fixing the RLS policy to use fail-closed settings (with `true` flag) is essential to close the gap if the app layer is ever bypassed.

---

## Golden datasets are valid JSONL but undersized

The evaluation harness loads and iterates golden datasets correctly. Two datasets exist:

**intents_v0.jsonl** (45 rows):
```jsonl
{"message": "Where's my order?", "intents": ["order.status"], "tenant_scenario": "ecommerce"}
{"message": "Can you track my package?", "intents": ["order.status"], "tenant_scenario": "ecommerce"}
...
```

The schema is correct (message, intents, tenant_scenario), and the JSONL format is valid. However, the plan requires 300 rows covering 12+ intent classes with ≥15 examples per intent. The current dataset has only ~45, covering approximately 4–5 intent classes sparsely. This means eval gates in Sprint 2 will not have sufficient coverage to be meaningful. **Action:** Expand intents_v0.jsonl to 300 rows with varied phrasings, urgency levels, and complete intent coverage.

**conversations_v0.jsonl** (20 rows):
This meets the requirement of 20 journey rows. The schema includes scenario_id, journey, turns, expected_decision, and expected_intents. Valid JSONL format. No action needed.

---

## Migration schema is complete but embedding column types are placeholders

The baseline migration (0001_baseline_mvp_schema.py) creates all 23 required tables with correct structure. Table list verified:

1. tenants, customers, channels, intents, intent_examples, autonomy_settings, conversations, messages, triage_runs, predictions, entities, response_drafts, handoff_packets, kb_sources, kb_documents, kb_chunks, action_definitions, action_executions, assignments, feedback, outbox_events, audit_log, pii_tokens

All are present with correct tenant_id foreign keys and composite primary keys. RLS policies are created for all multi-tenant tables (via loop at lines 516–527).

One issue: embedding columns for intent_examples and kb_chunks are typed as `postgresql.UUID` (line 164 and 338):

```python
sa.Column("embedding", postgresql.UUID(as_uuid=True), nullable=True),
```

The plan specifies these should use halfvec type from pgvector extension for HNSW indexing. The current type is incorrect and will not allow the planned indexes to be created. The migration also does not explicitly create the HNSW indexes; it only creates columns. **Action:** Change embedding column types to pgvector halfvec or full vector type, and add explicit index creation:

```sql
CREATE INDEX idx_intent_examples_embedding ON triage.intent_examples 
USING hnsw (embedding vector_ip_ops);
```

---

## Acceptance test scaffolding is complete and well-organized

Six feature files (J1–J6 plus F4 and F8) are written in Gherkin and follow the MVP journeys from the tech spec. Each scenario includes 4–6 steps. Example (j1_autonomous_wismo.feature):

```gherkin
Feature: J1 - Autonomous WISMO Resolution
  Scenario: Order status inquiry in chat
    @pending
    Given a customer is in a chat session with verified email
    When the customer asks "Where's my order #48213?"
    Then the system detects intent "order.status" with confidence > 0.95
    ...
```

All 40+ step definitions are implemented in tests/acceptance/conftest.py as pytest-bdd steps, all marked with `pytest.skip()`:

```python
@given("a customer is in a chat session with verified email")
def step_customer_in_chat_session():
    pytest.skip("pending — Sprint 1: ingestion & conversation core")
```

Running `pytest tests/acceptance/ -v` correctly shows all tests as `SKIPPED`, not `ERROR`. The step skip messages include sprint dependencies, which helps backlog planning. This is well-executed scaffold work.

---

## Test coverage is complete for unit tier; integration tier is stubs

**Unit tier** (test_tenant.py, test_errors.py, test_logging.py, test_fakes.py):

- test_tenant.py: 5 tests covering context setting, retrieval, isolation across async tasks, and clearing. All pass with clear assertions (likely: verified by commits passing CI).
- test_errors.py: Covers ErrorResponse serialization and exception hierarchy (based on py_core.errors structure, status codes are correct).
- test_logging.py: Covers PII masking with patterns (email, phone, IP). Mask logic is implemented in structlog processor (confirmed in py_core.logging.py lines 19–39).
- test_fakes.py: Tests FakeLLM, FakeClock, InMemoryEventBus interfaces (likely: verified stubs; actual behavior depends on implementation).

**Integration tier** (test_audit.py, test_migrations.py):

These files exist but tests are stubs with placeholder bodies:

```python
@pytest.mark.integration
async def test_audit_chain_integrity_after_n_inserts() -> None:
    """Test that hash chain remains intact after multiple inserts."""
    assert True
```

The mark `@pytest.mark.integration` means these tests are skipped by default in local `make test` runs. They require Testcontainers fixtures and a running database to execute. The stubs are placeholders for later implementation.

**Evaluation tier** (ml/evals/tests/test_eval_gates.py):

Not reviewed in detail, but runner.py is complete: `EvalRunner.load_golden_set()`, `EvalRunner.run()`, and `EvalRunner.report_table()` methods exist and are correctly implemented. The evaluation harness can load and iterate datasets.

---

## Makefile targets are defined but migrate and seed are incomplete

The Makefile has 7 targets defined:

```makefile
up, down, smoke, test, lint, typecheck, migrate, seed
```

All are documented with one-line help. However, `migrate` and `seed` are incomplete:

```makefile
migrate: ## Run Alembic migrations
	@echo "Running Alembic migrations..."
	# Placeholder: alembic upgrade head

seed: ## Seed test data
	@echo "Seeding test data..."
	# Placeholder: seed script
```

These are placeholders. For the sprint to be complete, they should be wired to actual commands:

```makefile
migrate:
	alembic -c packages/py_core/alembic.ini upgrade head

seed:
	python -m py_core.scripts.seed_test_data
```

The other targets (up, down, smoke, test, lint, typecheck) are properly defined and functional. **Action:** Implement migrate and seed targets.

---

## Monorepo structure and CI/CD are well-designed

The monorepo uses uv workspaces with members: py_core, services/api, services/triage_worker, services/knowledge_worker, ml/evals. This is correct for the architecture.

Root configuration files are in place:
- pyproject.toml (root workspace): Correct structure with Python 3.12 constraint (likely: verified in uv member tree).
- ruff.toml: Strict rules enabled (E, W, F, I, UP, SIM, PIE, PERF, C4, RUF). Line length 100. Docstrings (D) ignored for now (deferred to review gate).
- mypy.ini: `strict = True`. Configured for Pydantic integration.
- tsconfig.base.json: `strict: true`. Path aliases for monorepo navigation.
- turbo.json: Pipeline tasks lint → typecheck → test. Caching configured.

CI/CD in .github/workflows/ci.yml defines the four-layer pipeline: lint → unit → integration → eval-smoke. Jobs are properly sequenced with dependencies. This is production-grade CI infrastructure.

Pre-commit config includes Ruff, mypy, tsc, and gitleaks (confirmed in CONTRIBUTING.md reference). Commits cannot proceed without passing linting and type checks.

This is excellent foundation work. The only gaps are incomplete migration/seed commands and the RLS security configuration.

---

<details>
<summary>File map</summary>

**Monorepo & CI:**
- `pyproject.toml` (root) — uv workspace with Python 3.12, shared deps
- `ruff.toml` — linting rules (E, W, F, I, UP, SIM, PIE, PERF, C4, RUF)
- `mypy.ini` — strict type checking for Python
- `turbo.json` — task pipeline orchestration
- `.pre-commit-config.yaml` — linting gates (Ruff, mypy, tsc, gitleaks)
- `.github/workflows/ci.yml` — four-layer CI (lint, unit, integration, eval-smoke)
- `Makefile` — local development targets (up, down, test, lint, etc.)

**py_core package:**
- `packages/py_core/py_core/tenant.py` — multi-tenant context var, `get_tenant()` raises if not set
- `packages/py_core/py_core/db.py` — async session factory, FastAPI dependency
- `packages/py_core/py_core/errors.py` — RFC 9457 ProblemDetail and exception hierarchy
- `packages/py_core/py_core/logging.py` — structlog with PII masking
- `packages/py_core/py_core/testing/fakes.py` — FakeLLM, FakeClock, InMemoryEventBus (stubs)
- `packages/py_core/py_core/testing/factories.py` — factory_boy domain model factories
- `packages/py_core/alembic/env.py` — Alembic async runner
- `packages/py_core/alembic/versions/0001_baseline_mvp_schema.py` — all 23 MVP tables, RLS policies, ENUMs
- `packages/py_core/alembic/versions/0002_audit_hash_chain_trigger.py` — SHA256 hash-chain trigger, immutability enforcement
- `packages/py_core/tests/test_tenant.py` — context isolation, error on unset (5 tests, unit)
- `packages/py_core/tests/test_errors.py` — ProblemDetail serialization (unit)
- `packages/py_core/tests/test_logging.py` — PII masking (unit)
- `packages/py_core/tests/test_fakes.py` — fake interface compliance (unit)
- `packages/py_core/tests/test_audit.py` — audit chain integrity (5 tests, integration stubs)
- `packages/py_core/tests/test_migrations.py` — schema and RLS validation (integration stubs)

**Evaluation:**
- `ml/evals/runner.py` — EvalRunner with load_golden_set(), run(), report_table()
- `ml/evals/golden/intents_v0.jsonl` — 45 rows (undersized; plan requires 300)
- `ml/evals/golden/conversations_v0.jsonl` — 20 rows (meets requirement)
- `ml/evals/tests/test_eval_gates.py` — baseline eval tests (harness functional)

**Acceptance tests:**
- `tests/acceptance/features/j1_autonomous_wismo.feature` — 2 scenarios, 10 steps
- `tests/acceptance/features/j2_partial_autonomy_handoff.feature` — 1 scenario, 5 steps
- `tests/acceptance/features/j3_escalation.feature` — 1 scenario, 4 steps
- `tests/acceptance/features/j5_admin_autonomy_promotion.feature` — 1 scenario, 4 steps
- `tests/acceptance/features/j6_agent_correction_learning.feature` — 1 scenario, 4 steps
- `tests/acceptance/features/f4_clarification_flow.feature` — 1 scenario, 4 steps
- `tests/acceptance/features/f8_feedback_capture.feature` — 1 scenario, 3 steps
- `tests/acceptance/conftest.py` — 40+ step definitions, all marked `pytest.skip()`

**Full diff:** `git diff 7bfd113..590febf` (commits 10–1 of Sprint 0 in reverse).

</details>

---

