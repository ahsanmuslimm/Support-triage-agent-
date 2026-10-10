# Sprint 0 Implementation Plan — Triage Agent MVP Foundation

**Project:** AI-Powered Customer Support Triage Agent  
**Stage:** MVP (Stage 1)  
**Sprint:** 0 — Foundation & Test Harness  
**Duration:** 1 week (7 working days)  
**Objective:** Build complete foundational infrastructure for the Triage Agent MVP — no feature work, only plumbing.

**Key Principle:** Every deliverable leaves the codebase in a buildable, testable state. Tests are written first for Tier-A (strict TDD) items; verification commands are the project's actual build and test tooling.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Sprint 0 Deliverables (0.1–0.9)](#sprint-0-deliverables-01--09)
3. [File Structure Created](#file-structure-created)
4. [Commit Order](#commit-order)

---

## Architecture Overview

**Stack:**
- **Language:** Python 3.12 (backend) + TypeScript 5.3 (frontend/CLI)
- **Package Manager:** uv (Python workspace manager)
- **Monorepo:** uv workspaces + Turborepo for orchestration
- **Linting/Type:** Ruff + mypy --strict (Python), tsc --strict (TypeScript)
- **CI/CD:** GitHub Actions (layered: unit → integration → eval-smoke → e2e)
- **Database:** PostgreSQL 18 + pgvector (local: Testcontainers; infra: managed RDS)
- **Cache:** Redis 7 (local: docker-compose; infra: ElastiCache)
- **Storage:** MinIO (local; infra: S3)
- **Test Framework:** pytest + pytest-asyncio (Python), vitest (TypeScript)
- **LLM Access:** LiteLLM proxy (unified routing, fallbacks, budgets)

**Deployables (stubs in Sprint 0):**
- `services/api` — FastAPI application
- `services/triage_worker` — LangGraph worker (async background job)
- `services/knowledge_worker` — Knowledge indexing/retrieval service
- `apps/console` — Next.js admin/ops dashboard
- `apps/widget` — Preact web chat widget (static asset)
- `ml/evals` — Evaluation harness and golden datasets

---

## Sprint 0 Deliverables (0.1–0.9)

### 0.1 Monorepo Scaffold

**Objective:** Establish a uv + Turborepo monorepo with Python and TypeScript, strict linting and type checking on every commit.

**Files to create:**

1. **`pyproject.toml`** (root)
   - uv workspace with members: `packages/py_core`, `services/api`, `services/triage_worker`, `services/knowledge_worker`, `ml/evals`
   - Python version constraint: `python = "^3.12"`
   - Shared dependencies: `sqlalchemy[asyncio]`, `pydantic`, `structlog`, `opentelemetry-api`, `opentelemetry-sdk`
   - Optional groups: `dev` (pytest, mypy, ruff), `test` (testcontainers, pytest-asyncio)

2. **`ruff.toml`** (root)
   - Line length: 100
   - Target Python: 3.12
   - Rules enabled: E, W, F, I, UP, SIM, PIE, PERF, C4, RUF
   - Ignore: D (docstrings for now — will be enforced at review gate)
   - Per-path rules: `tests/` and `**/test_*.py` exclude S101 (assert), B101 (pytest.raises)
   - Include all packages and services in source roots

3. **`mypy.ini`** (root)
   - `python_version = 3.12`
   - `strict = True` — enforce full strict mode
   - `warn_unused_configs = True`
   - Per-module: `ignore_errors = False` for all modules under `packages/py_core` and `services/`
   - Plugins: `pydantic.mypy` for SQLAlchemy/Pydantic integration

4. **`tsconfig.base.json`** (root)
   - `strict: true`
   - `target: ES2022`, `module: ESNext`
   - Path aliases: `@/*` → `./apps/*`, `@services/*` → `./services/*`
   - `declaration: true`, `declarationMap: true`

5. **`turbo.json`** (root)
   - Pipeline tasks: `lint`, `typecheck`, `test`, `build`
   - Cache outputs: `.turbo`, `dist/`, `build/`, `.pytest_cache`
   - Task dependencies: `typecheck` depends on `^build`; `test` depends on `^typecheck`
   - Caching rules: include `ruff.toml`, `mypy.ini`, `tsconfig.base.json` in inputs

6. **`.pre-commit-config.yaml`** (root)
   - `ruff` check + fix (Python)
   - `mypy` on `packages/py_core/**/*.py` and `services/**/*.py`
   - `tsc --noEmit` on all `*.ts` files
   - `gitleaks` for secrets scanning (fail on critical)
   - Run on every commit before staging

7. **`Makefile`** (root)
   - Targets:
     - `up` — `docker-compose -f tools/docker-compose.yml up -d`
     - `down` — `docker-compose -f tools/docker-compose.yml down`
     - `smoke` — run package smoke tests (linting + basic imports)
     - `test` — `pytest tests/ -v` (all tests)
     - `lint` — `ruff check packages/ services/ apps/ ml/`
     - `typecheck` — `mypy packages/ services/`
     - `migrate` — run Alembic migrations (added in 0.5)
     - `seed` — seed test data (added in 0.5)
   - Each target is idempotent

8. **`README.md`** (root)
   - Project overview (2–3 sentences)
   - Table documenting every `make` target with one-line description and example output
   - Prerequisites: Python 3.12, uv, Docker (for local stack)
   - Quick start: `make up && make smoke`
   - Link to CONTRIBUTING.md

9. **`CONTRIBUTING.md`** (root)
   - TDD discipline per Tier (A/B/C/D/E from implementation plan)
   - Definition of Ready: story includes tier classification and test-first artefact
   - Definition of Done: code passes pre-commit, `make lint && make typecheck && make test`, feature branch is pushed and PR created
   - Commit message format: Conventional Commits (feat/fix/test/docs/chore)
   - Branch naming: `feat/story-name`, `fix/bug-name`

**Verification:**
```bash
cd d:\WORKING\PORTFOLIO\FEATURED\ PROJECTS\Support-triage-agent-
make lint  # Ruff passes on empty stub packages
make typecheck  # mypy --strict passes on empty stub packages
```

Expected: Both commands complete with exit code 0, no errors.

---

### 0.2 Local Docker Compose Stack

**Objective:** Define a development stack with all backing services (Postgres, Redis, MinIO, LiteLLM, Langfuse, Mailpit).

**File to create:**

1. **`tools/docker-compose.yml`**
   - Services:
     - `postgres:18-alpine` with pgvector extension, port 5432
     - `redis:7-alpine` (or `valkey:7-alpine`), port 6379
     - `minio/minio:latest`, port 9000 (API) + 9001 (console)
     - `mailpit:latest`, port 1025 (SMTP), 8025 (web)
     - `langfuse/langfuse:latest`, port 3000, PostgreSQL backend
     - `litellm/litellm:latest` (self-hosted), port 8000, mounted config from `tools/litellm.yaml`
   - Environment variables: sourced from `.env.local` (git-ignored)
   - Health checks: all services include `healthcheck` blocks; top-level `depends_on` uses them
   - Volumes: `pgdata` for Postgres persistence, `miniodata` for object storage
   - Init scripts:
     - For Postgres: SQL script to create `pgvector` extension and the `triage_app` role
     - For MinIO: setup script to create the `triage` bucket

2. **`.env.example`** (root)
   - Template for `.env.local` (not committed)
   - Variables:
     - `PG_HOST=localhost`, `PG_PORT=5432`, `PG_DB=triage`, `PG_USER=postgres`, `PG_PASSWORD=postgres_dev`
     - `REDIS_HOST=localhost`, `REDIS_PORT=6379`
     - `MINIO_ENDPOINT=http://localhost:9000`, `MINIO_ACCESS_KEY=minioadmin`, `MINIO_SECRET_KEY=minioadmin`
     - `LITELLM_API_KEY=sk-1234` (dummy for local testing)
     - `LANGFUSE_PUBLIC_KEY=pk_xxx`, `LANGFUSE_SECRET_KEY=sk_xxx` (dummies)
     - `ENVIRONMENT=local`
     - `LOG_LEVEL=DEBUG`

3. **`tools/litellm.yaml`**
   - LiteLLM configuration for local testing with mocked providers
   - Routes: `/v1/chat/completions` → fallback mock adapter
   - Budget limits: $100/day default
   - Cost tracking enabled
   - Example model aliases for testing

**Verification:**
```bash
make up
# Wait 10 seconds for health checks
curl -s http://localhost:5432/ && echo "Postgres running" || echo "Postgres not ready"
curl -s http://localhost:6379/  && echo "Redis running" || echo "Redis not ready"
curl -s http://localhost:9000/minio/health/live && echo "MinIO running" || echo "MinIO not ready"
make down
```

Expected: All services report "running"; curl returns 200 or connection success.

---

### 0.3 GitHub Actions CI Skeleton

**Objective:** Define CI pipeline with four-layer job structure (unit → integration → eval-smoke → e2e) and security scanning.

**Files to create:**

1. **`.github/workflows/ci.yml`**
   - Triggers: on push (to any branch) and on PR
   - Concurrency: cancel in-flight runs for the same PR
   - Jobs (in order):
     - **Job 1: Lint & typecheck** (runs on every push, < 2 min)
       - Steps: checkout, setup Python 3.12, setup Node 20, install uv, run `make lint`, run `make typecheck`
       - Cache: uv cache, node_modules (npm), turbo cache
     - **Job 2: Unit tests** (runs on every push, < 3 min)
       - Steps: checkout, setup Python 3.12, setup Node 20, install uv, docker-compose up, run `pytest tests/unit -v --cov=packages/py_core --cov=services --cov-report=term-missing`
       - Cache: uv, node_modules, turbo, pytest cache
       - Fail on coverage < 80% for core modules
     - **Job 3: Integration tests** (runs on PR only, < 10 min)
       - Steps: checkout, setup Python/Node, install uv, docker-compose up, run `pytest tests/integration -v -m integration`
       - Cache: same as unit
       - Requires: successful lint + unit jobs
     - **Job 4: Eval smoke** (runs on PR only, < 5 min)
       - Steps: checkout, setup Python/Node, install uv, docker-compose up, run `pytest ml/evals/tests/ -v -m eval --cassettes-mode=none`
       - Uses VCR cassettes (recorded, not live LLM calls)
       - Requires: successful integration job
     - **Job 5: E2E tests** (runs on merge to main only, < 15 min)
       - Steps: checkout, setup Python/Node, install uv, docker-compose up, run `pytest tests/acceptance/ -v --headless`
       - Requires: all prior jobs pass
   - Additional jobs (parallel to main pipeline):
     - **Gitleaks:** scan for secrets, fail on critical
     - **Semgrep:** SAST scanning with custom rule set for LLM safety patterns
     - **Trivy:** scan Docker images and dependencies
   - All jobs cache dependencies to keep runtime under budget
   - Artifacts: test results, coverage reports (uploaded to CodeCov)

2. **`.github/workflows/composite-actions/setup-python-env.yaml`**
   - Composite action to set up Python 3.12, uv, and all caches
   - Inputs: `python-version` (default 3.12), `cache-key-prefix`
   - Outputs: `cache-hit` boolean

3. **`.github/workflows/composite-actions/docker-compose-up.yaml`**
   - Composite action to start services and wait for health checks
   - Services: postgres, redis, minio (omit langfuse/litellm for unit tests)

**Verification:**
```bash
# Push to a new branch
git checkout -b test/ci
git push origin test/ci
# Watch GitHub Actions → ci.yml
# Expected: all 4 jobs pass in sequence with green checkmarks
```

Expected: Lint and unit jobs complete in < 3 min; integration in < 10 min.

---

### 0.4 py_core Package — Foundational Modules

**Objective:** Create the shared Python library with tenant context, database session management, error handling, observability and logging.

**Files to create:**

1. **`packages/py_core/pyproject.toml`**
   - Package name: `py-core`
   - Version: 0.1.0 (will be managed by a release process later)
   - Dependencies: `sqlalchemy[asyncio]>=2.0`, `pydantic>=2.0`, `structlog>=24.0`, `opentelemetry-api>=1.21`, `opentelemetry-sdk>=1.21`, `opentelemetry-exporter-otlp>=0.42b0`, `python-json-logger>=2.0`
   - Dev dependencies: `pytest>=7.0`, `pytest-asyncio>=0.21`, `mypy>=1.7`
   - Includes package discovery of modules under `py_core/`

2. **`packages/py_core/py_core/__init__.py`**
   - Exports: `set_tenant`, `get_tenant`, `MissingTenantContext`, `SessionFactory`, `ErrorResponse`, `init_otel`, `configure_logging`

3. **`packages/py_core/py_core/tenant.py`** (Tier A — strict TDD)
   - Context var: `_current_tenant_id: ContextVar[UUID | None]`
   - `set_tenant(tenant_id: UUID) → None` — sets the context var
   - `get_tenant() → UUID` — returns tenant ID or raises `MissingTenantContext` if not set
   - SQLAlchemy event listener on `before_execute` that injects `SET LOCAL app.tenant_id = $1` before every SQL statement (only in a session context)
   - Tests:
     - ✅ `test_get_tenant_not_set_raises_error()` — `MissingTenantContext` is raised
     - ✅ `test_set_and_get_tenant()` — tenant is set and retrieved
     - ✅ `test_tenant_isolation_across_coroutines()` — two async tasks have independent tenant contexts
     - ✅ `test_set_local_injected_exactly_once_per_statement()` — statement count is 2 (SET LOCAL + query), not 3

4. **`packages/py_core/py_core/db.py`** (Tier A)
   - `AsyncSessionFactory` — creates `AsyncSession` with tenant context injection
   - `get_db_session() → AsyncGenerator[AsyncSession]` — FastAPI dependency that yields a session with tenant already set (assumes `set_tenant()` was called upstream)
   - Context manager: `with session_context(tenant_id)` — sets tenant, creates session, yields, then cleans up
   - Tests:
     - ✅ `test_session_context_manager_sets_tenant()` — tenant is injected in SET LOCAL
     - ✅ `test_session_context_manager_cleans_up_on_error()` — session is rolled back on exception
     - ✅ `test_fastapi_dependency_requires_tenant()` — calling without `set_tenant()` raises `MissingTenantContext`

5. **`packages/py_core/py_core/errors.py`** (Tier A)
   - `ErrorResponse` (RFC 9457 Problem Details):
     ```python
     class ErrorResponse(BaseModel):
       type: str  # e.g., "urn:triage:invalid_entity"
       title: str  # "Invalid Entity"
       status: int  # 400
       detail: str  # "Order ID 12345 not found in Shopify"
       instance: str | None  # "/v1/conversations/123/messages"
     ```
   - `TriageError` — base domain exception (inherits `Exception`, has `error_code: str` and `detail: str`)
   - Subclasses: `MissingTenantContext`, `EntityNotFound`, `UnauthorizedAction`, `InvalidIdempotencyKey`, `RateLimitExceeded`
   - FastAPI exception handler registered with `@app.exception_handler(TriageError)`
   - Tests:
     - ✅ `test_error_response_serializes_to_json()` — all fields are present
     - ✅ `test_exception_handler_returns_problem_details()` — FastAPI receives correct status code and JSON shape

6. **`packages/py_core/py_core/otel.py`** (Tier A)
   - `init_otel(service_name: str, environment: str) → tuple[Tracer, Meter]`
   - Tracer provider with OTLP exporter (endpoint from env var `OTEL_EXPORTER_OTLP_ENDPOINT`)
   - Meter provider with same exporter
   - Logger provider with same exporter
   - Spans include tenant_id and request_id from context vars
   - Tests:
     - ✅ `test_otel_init_creates_providers()` — all three providers are initialized
     - ✅ `test_otlp_exporter_configured()` — exporter endpoint is set from env
     - ✅ `test_span_includes_tenant_context()` — spans carry tenant_id attribute

7. **`packages/py_core/py_core/logging.py`** (Tier A + C)
   - `configure_logging(environment: str) → None`
   - In production: JSON renderer (structlog.processors.JSONRenderer)
   - In development: color console renderer (structlog.dev.ConsoleRenderer)
   - PII-free processor that masks known fields:
     - Email: `user@example.com` → `[email_hash: abc123]`
     - Phone: `+1 555 0100` → `[phone_hash: def456]`
     - Name fields (first_name, last_name, customer_name): `John Doe` → `[name_hash: ghi789]`
   - Context processors add `request_id`, `tenant_id`, `trace_id` from context vars
   - Tests (Tier C evaluation):
     - ✅ `test_pii_masking_email()` — email is masked before logging
     - ✅ `test_pii_masking_phone()` — phone is masked
     - ✅ `test_pii_recall_on_evaluation_set()` — PII-masking recall ≥ 0.95 on 200 samples

**Verification:**
```bash
cd packages/py_core
make lint
make typecheck
make test
# Expected: all tests pass, coverage ≥ 90%
```

---

### 0.5 Alembic Baseline Migration

**Objective:** Create the MVP subset of the schema (§32 of tech spec) with full RLS policies and HNSW indexes.

**Files to create:**

1. **`packages/py_core/alembic/env.py`**
   - Async context for running migrations
   - Target metadata: `Base.metadata` from `py_core.models`
   - Auto-generate migrations on `revision_autogenerate`

2. **`packages/py_core/alembic/versions/0001_baseline_mvp_schema.py`**
   - Creates all tables listed in §0.5 of the implementation plan:
     - **Tenancy:** `tenants` (id UUID PK, slug, name, config JSONB, created_at, updated_at)
     - **Customers:** `customers` (tenant_id, id UUID, external_id, email_hash, phone_hash, name_pseudonym, ltv_cents, tier, created_at, updated_at) with composite PK
     - **Channels:** `channels` (tenant_id, id UUID, type ENUM, config JSONB, enabled, created_at)
     - **Intents:** `intents` (tenant_id, id UUID, key, parent_id, label, autonomy_default, human_only, created_at) + `intent_examples` with halfvec(1024)
     - **Autonomy:** `autonomy_settings` (tenant_id, intent_id, channel_type, segment, level, threshold_auto, threshold_draft, kill_switch, updated_at)
     - **Conversations:** `conversations` (tenant_id, id UUID, customer_id, channel_id, status, resolution_type, reopened_72h, csat_score, timestamps)
     - **Messages:** `messages` (tenant_id, id UUID, conversation_id, direction, role, body_ciphertext, body_iv, dek_version, pseudonymized_body, provider_msg_id UNIQUE, idempotency_key UNIQUE, coalesced_into, created_at)
     - **Triage Runs:** `triage_runs` (tenant_id, id UUID, conversation_id, message_id, status, decision, autonomy_level, guard_scores JSONB, llm_cost_usd, timestamps)
     - **Predictions:** `predictions` (tenant_id, id UUID, run_id, intent_id, confidence, source, created_at)
     - **Entities:** `entities` (tenant_id, id UUID, run_id, type, raw_value_hash, verified, owner_match, created_at)
     - **Drafts:** `response_drafts` (tenant_id, id UUID, run_id, body_ciphertext, body_iv, dek_version, outcome, edit_ratio, created_at)
     - **Handoffs:** `handoff_packets` (tenant_id, id UUID, run_id, packet_json JSONB, created_at)
     - **KB:** `kb_sources`, `kb_documents`, `kb_chunks` (with halfvec(1024) embedding + audience ENUM)
     - **Actions:** `action_definitions`, `action_executions`
     - **Assignments:** `assignments` (tenant_id, id UUID, conversation_id, agent_id, timestamps)
     - **Feedback:** `feedback` (tenant_id, id UUID, conversation_id, run_id, type ENUM, payload JSONB, created_at)
     - **Outbox:** `outbox_events` (id UUID PK, tenant_id, aggregate_type, aggregate_id, event_type, payload JSONB, created_at, published_at)
     - **Audit:** `audit_log` (id BIGSERIAL PK, tenant_id, actor_id, actor_type, action, target_type, target_id, payload, created_at, prev_hash, row_hash)
     - **Vault:** `pii_tokens` (tenant_id, id UUID, token UNIQUE, entity_type, ciphertext, iv, dek_version, created_at)
   - RLS policies: for every multi-tenant table, enable `ENABLE ROW LEVEL SECURITY` with policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)`
   - HNSW indexes on `intent_examples.embedding` and `kb_chunks.embedding` (ops: halfvec_ip_ops)
   - Composite indexes on `(tenant_id, id)` for foreign-key lookups
   - Role creation: `CREATE ROLE triage_app WITH LOGIN; ALTER ROLE triage_app SET app.tenant_id = ...;`

3. **`packages/py_core/alembic/versions/0002_audit_hash_chain_trigger.py`** (see 0.6)

**Tests (Tier A — run against Testcontainers Postgres):** (placed in `packages/py_core/tests/test_migrations.py`)
- ✅ `test_migration_0001_creates_all_tables()` — all table names exist in `information_schema`
- ✅ `test_rls_enabled_on_tenant_tables()` — `pg_class.relrowsecurity` is true for multi-tenant tables
- ✅ `test_rls_policy_blocks_cross_tenant_read()` — tenant A selects rows created by tenant B and gets 0 rows
- ✅ `test_rls_policy_blocks_cross_tenant_update()` — UPDATE from tenant A on tenant B's rows succeeds but affects 0 rows
- ✅ `test_hnsw_indexes_created()` — `intent_examples.embedding` and `kb_chunks.embedding` have indexes
- ✅ `test_app_role_has_no_bypassrls()` — `pg_roles.bypassrls` is false for `triage_app`
- ✅ `test_migration_is_idempotent()` — running migration twice does not error

**Verification:**
```bash
cd packages/py_core
make migrate  # Alembic upgrade head
pytest tests/test_migrations.py -v
# Expected: all 7 tests pass
```

---

### 0.6 Audit Hash-Chain Trigger

**Objective:** Implement immutable audit log with hash-chain integrity verification.

**File to create:**

1. **`packages/py_core/alembic/versions/0002_audit_hash_chain_trigger.py`**
   - PL/pgSQL function `audit_hash_chain()` called BEFORE INSERT on `audit_log`
   - On each insert:
     - Look up the latest `row_hash` for the tenant (SELECT MAX(id) WHERE tenant_id = ...)
     - Compute `row_hash = encode(sha256(prev_hash || tenant_id::text || actor_id || action || target_id || payload::text || created_at::text), 'hex')`
     - If no prior row, `prev_hash = 'genesis'`
     - Assign NEW.prev_hash, NEW.row_hash, NEW.created_at (current time)
   - BEFORE UPDATE trigger on `audit_log` that raises exception (UPDATE forbidden)
   - BEFORE DELETE trigger on `audit_log` that raises exception (DELETE forbidden)
   - Verification function: `verify_audit_chain(tenant_id UUID) RETURNS TABLE(broken_at BIGINT, expected TEXT, found TEXT)`
     - Walks the chain: start with 'genesis', for each row compute expected hash, compare with stored, collect mismatches
     - Returns empty if chain is intact

2. **`packages/py_core/py_core/audit.py`** (Tier A)
   - Python wrapper: `verify_audit_chain(session: AsyncSession, tenant_id: UUID) → list[AuditBreak]`
   - AuditBreak dataclass with `broken_at`, `expected_hash`, `found_hash`

**Tests (Tier A):** (in `packages/py_core/tests/test_audit.py`)
- ✅ `test_audit_chain_integrity_after_n_inserts()` — insert 10 rows, verify_audit_chain returns empty list
- ✅ `test_audit_chain_detects_tampered_payload()` — manually update a row's payload (using superuser), verify_audit_chain identifies broken link
- ✅ `test_audit_update_is_forbidden()` — UPDATE raises exception from trigger
- ✅ `test_audit_delete_is_forbidden()` — DELETE raises exception from trigger
- ✅ `test_first_row_prev_hash_is_genesis()` — first row has prev_hash = 'genesis'

**Verification:**
```bash
cd packages/py_core
make migrate  # Applies migration 0002
pytest tests/test_audit.py -v
# Expected: all 5 tests pass
```

---

### 0.7 Test Kit — Fakes, Factories & Fixtures

**Objective:** Build reusable testing infrastructure: fakes, factories, Testcontainers fixtures, cassette recorder.

**Files to create:**

1. **`packages/py_core/py_core/testing/__init__.py`**
   - Exports: `FakeLLM`, `FakeClock`, `InMemoryEventBus`, factories, fixtures

2. **`packages/py_core/py_core/testing/fakes.py`** (Tier A)
   - `FakeLLM` — implements LiteLLM adapter interface:
     - `__init__(scripted_responses: dict[tuple[str, str], str])` — keyed by (prompt_name, scenario)
     - `async def chat_completion(prompt: str, ...) → ChatCompletionResponse` — looks up prompt_name in scenario, returns scripted output or raises
     - `call_log: list[LLMCall]` — records all calls for assertions
     - `async def reset()` — clears call log
     - Tests:
       - ✅ `test_fake_llm_returns_scripted_output()` — correct scenario key returns registered output
       - ✅ `test_fake_llm_raises_on_unknown_scenario()` — unknown key raises `UnknownScenarioError`
       - ✅ `test_fake_llm_records_calls()` — call_log includes all invocations

   - `FakeClock` — injectable time:
     - `__init__(initial_time: datetime)` — starts at a fixed time
     - `now() → datetime` — returns current frozen time
     - `advance(seconds: int) → None` — moves time forward
     - Tests:
       - ✅ `test_fake_clock_returns_same_time()` — multiple calls return same value
       - ✅ `test_fake_clock_advances_by_seconds()` — advance(30) increases by 30 s

   - `InMemoryEventBus` — implements EventBus port:
     - `async def publish(event: Event) → None` — appends to list
     - `events: list[Event]` — all published events
     - `async def reset()` — clears list
     - Helper: `assert_published(event_type: str, payload_subset: dict)` — filters and checks
     - Tests:
       - ✅ `test_in_memory_event_bus_publishes_events()` — events are stored
       - ✅ `test_assert_published_filters_correctly()` — payload matching works

3. **`packages/py_core/py_core/testing/factories.py`**
   - Uses `factory_boy` library (add to `py_core` dev dependencies)
   - Factories:
     ```python
     class TenantFactory(factory.Factory):
       id = factory.LazyFunction(uuid.uuid4)
       slug = factory.Faker('slug')
       name = factory.Faker('company')
       ...
     
     class CustomerFactory(factory.Factory):
       tenant_id = factory.SubFactory(TenantFactory)
       id = factory.LazyFunction(uuid.uuid4)
       email_hash = factory.Faker('sha256')
       ...
     
     # Similarly: ConversationFactory, MessageFactory, TriageRunFactory, IntentFactory, AuditLogFactory
     ```

4. **`packages/py_core/tests/conftest.py`**
   - Pytest conftest with shared fixtures:
     ```python
     @pytest_asyncio.fixture
     async def pg_container():
       # Start Testcontainers Postgres 18 + pgvector
       # Run migrations
       # Yield async engine
       # Teardown
     
     @pytest_asyncio.fixture
     async def redis_container():
       # Start Testcontainers Redis 7
       # Yield redis.asyncio.Redis client
       # Teardown
     
     @pytest.fixture
     def fake_llm():
       return FakeLLM(scripted_responses={})
     
     @pytest.fixture
     def fake_clock():
       return FakeClock(datetime.now(timezone.utc))
     ```

5. **`packages/py_core/py_core/testing/cassette_recorder.py`**
   - Thin wrapper around `pytest-recording` (VCR.py):
     ```python
     def cassette(path: str, record_mode: str = "none"):
       # Decorator for test functions
       # record_mode: "none" (replay only) in CI, "new_episodes" locally
     ```

**Tests (Tier A):** (in `packages/py_core/tests/test_fakes.py`, `test_factories.py`)
- ✅ `test_tenant_factory_creates_unique_rows()` — two instances have different IDs
- ✅ `test_fake_llm_adheres_to_chat_completion_interface()` — matches LiteLLM contract

**Verification:**
```bash
cd packages/py_core
pytest tests/test_fakes.py tests/test_factories.py -v
# Expected: all tests pass
```

---

### 0.8 Eval Harness + Golden Datasets v0

**Objective:** Build evaluation infrastructure and initial golden-set datasets.

**Files to create:**

1. **`ml/evals/runner.py`** (Tier C)
   - `EvalRunner` class:
     - `load_golden_set(path: str) → list[EvalRow]` — reads JSONL
     - `run_evaluator(evaluator_fn, rows, metric_name) → MetricResult` — applies function to each row, collects results
     - `assert_gates(metrics: dict[str, MetricResult], thresholds: dict[str, float]) → None` — raises `EvalGateFailure` if any metric < threshold
     - `report_table(metrics, per_intent=True) → str` — formats results as ASCII table with per-intent slices
   - Pytest integration: `@pytest.mark.eval` decorator on test functions using runner
   - Example usage:
     ```python
     @pytest.mark.eval
     def test_intents_v0():
       runner = EvalRunner()
       rows = runner.load_golden_set("ml/evals/golden/intents_v0.jsonl")
       results = runner.run_evaluator(classifier.predict, rows, "top_1_accuracy")
       runner.assert_gates({"top_1_accuracy": results}, {"top_1_accuracy": 0.85})
     ```

2. **`ml/evals/conftest.py`**
   - Pytest fixture to skip eval tests by default (only run with `--eval` flag)
   - Cassette mode: set via `EVAL_CASSETTE_MODE` env var or `--cassettes-mode` CLI flag

3. **`ml/evals/golden/intents_v0.jsonl`**
   - 300 rows (synthetic, no real PII)
   - Schema: `{"message": "...", "intents": ["order.status", "shipping.delay", ...], "tenant_scenario": "ecommerce|saas"}`
   - Coverage:
     - 12+ intents from Appendix A (order.status, order.not_shipped, returns.request, returns.policy_question, refund.request, shipping.delay, billing.invoice_question, billing.tax_exemption, auth.sso_failure, auth.password_reset, account.plan_upgrade, account.cancel, how_to.feature_usage, how_to.integration, bug_report, human_only)
     - ≥ 15 rows per intent
     - Varied message length, phrasing, urgency
   - Example rows:
     ```jsonl
     {"message": "Where's my order #48213?", "intents": ["order.status"], "tenant_scenario": "ecommerce"}
     {"message": "I need a refund NOW this is unacceptable", "intents": ["refund.request"], "tenant_scenario": "ecommerce"}
     {"message": "How do I enable SSO?", "intents": ["how_to.feature_usage", "auth.sso_failure"], "tenant_scenario": "saas"}
     ```

4. **`ml/evals/golden/conversations_v0.jsonl`**
   - 20 rows covering journeys J1–J6 + edge cases
   - Schema: `{"scenario_id": "J1-01", "journey": "J1", "turns": [{"role": "customer", "content": "..."}], "expected_decision": "auto_resolve|route|escalate|clarify", "expected_intents": [...]}`
   - Example:
     ```jsonl
     {"scenario_id": "J1-01", "journey": "J1", "turns": [{"role": "customer", "content": "Where's my order?"}], "expected_decision": "auto_resolve", "expected_intents": ["order.status"]}
     ```

5. **`ml/evals/tests/test_eval_gates.py`**
   - Tests (Tier C — baseline gates):
     ```python
     @pytest.mark.eval
     def test_golden_intents_v0():
       # MVP baseline: thresholds set to values random classifier does NOT meet
       # This is intentional; gates will fail until Sprint 2 delivers the real classifier
       runner = EvalRunner()
       rows = runner.load_golden_set("golden/intents_v0.jsonl")
       # Stub classifier for now: returns equal confidence for all intents
       results = runner.run_evaluator(stub_classifier, rows, "top_1_accuracy")
       # Threshold is high (0.85) — should fail in Sprint 0, pass in Sprint 2
       runner.assert_gates({"top_1_accuracy": results}, {"top_1_accuracy": 0.85})
     
     @pytest.mark.eval
     def test_golden_conversations_v0():
       # Harness can load and iterate 20 scenarios without error
       runner = EvalRunner()
       rows = runner.load_golden_set("golden/conversations_v0.jsonl")
       assert len(rows) == 20
       for row in rows:
         assert "expected_decision" in row
         assert "expected_intents" in row
     ```

**Verification:**
```bash
cd ml/evals
pytest tests/test_eval_gates.py -v -m eval --cassettes-mode=none
# Expected: test_golden_conversations_v0 passes; test_golden_intents_v0 fails (intentional)
```

---

### 0.9 MVP Acceptance Scenarios as Pending Tests

**Objective:** Write all MVP journeys as executable Gherkin scenarios with step stubs that are skipped.

**Files to create:**

1. **`tests/acceptance/features/j1_autonomous_wismo.feature`**
   ```gherkin
   Feature: J1 - Autonomous WISMO Resolution
     As a customer
     I want to know where my order is
     So that I have visibility on delivery
   
     Scenario: Order status inquiry in chat
       Given a customer is in a chat session with verified email
       When the customer asks "Where's my order #48213?"
       Then the system detects intent "order.status" with confidence > 0.95
       And the system retrieves tracking from Shopify
       And the system composes a grounded answer with tracking link
       And the system sends the reply in < 4 seconds
       And the conversation is auto-resolved
       And a CSAT survey is sent
   ```

2. **`tests/acceptance/features/j2_partial_autonomy_handoff.feature`**
   ```gherkin
   Feature: J2 - Multi-intent with Partial Autonomy and Handoff
     Scenario: Refund request exceeds auto-limit
       Given a customer requests a refund for $240
       And the auto-refund limit is $150
       Then the system creates an approval request
       And the system notifies the customer of review status
       And a supervisor approves in Slack
       And the Temporal workflow executes the Stripe refund
       And the customer is confirmed
   ```

3. **`tests/acceptance/features/j3_escalation.feature`**, **`j5_admin_tuning.feature`**, **`j6_agent_correction.feature`** — similar structure

4. **`tests/acceptance/features/f4_clarification.feature`**
   ```gherkin
   Feature: F4 - Clarification Flow
     Scenario: Missing entity triggers clarification question
       Given a customer asks about an order without providing an order ID
       When the system needs an order ID to proceed
       Then the system asks one clarifying question
       And the customer provides the order ID
       And the system resolves the query
   ```

5. **`tests/acceptance/conftest.py`**
   - Pytest BDD step implementations (all marked with `@pytest.skip("pending — Sprint N")`):
     ```python
     @given("a customer is in a chat session with verified email")
     def step_customer_in_chat_session(context):
       pytest.skip("pending — Sprint 1: ingestion & conversation core")
     
     @when('the customer asks "{message}"')
     def step_customer_asks(context, message):
       pytest.skip("pending — Sprint 2: classification")
     
     # ... etc for all step types
     ```

**Tests (Tier D — all skipped):**
- ✅ All scenarios appear in `pytest --collect-only` output
- ✅ All steps are recognized (no `ERROR` in collection)
- ✅ Running `pytest tests/acceptance/ -v` shows all tests as `SKIPPED`, not `ERROR`

**Verification:**
```bash
pytest tests/acceptance/ --collect-only
# Expected: 8 scenarios × 4–6 steps each = ~40 step definitions, all collected
pytest tests/acceptance/ -v
# Expected: all tests appear as `SKIPPED`
```

---

## File Structure Created

After Sprint 0, the workspace structure is:

```
d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── composite-actions/
│           ├── setup-python-env.yaml
│           └── docker-compose-up.yaml
├── .pre-commit-config.yaml
├── .env.example
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml (root, uv workspace)
├── ruff.toml
├── mypy.ini
├── tsconfig.base.json
├── turbo.json
├── packages/
│   └── py_core/
│       ├── pyproject.toml
│       ├── py_core/
│       │   ├── __init__.py
│       │   ├── tenant.py
│       │   ├── db.py
│       │   ├── errors.py
│       │   ├── otel.py
│       │   ├── logging.py
│       │   ├── audit.py
│       │   └── testing/
│       │       ├── __init__.py
│       │       ├── fakes.py
│       │       ├── factories.py
│       │       └── cassette_recorder.py
│       ├── alembic/
│       │   ├── env.py
│       │   └── versions/
│       │       ├── 0001_baseline_mvp_schema.py
│       │       └── 0002_audit_hash_chain_trigger.py
│       └── tests/
│           ├── conftest.py
│           ├── test_tenant.py
│           ├── test_db.py
│           ├── test_errors.py
│           ├── test_otel.py
│           ├── test_logging.py
│           ├── test_audit.py
│           ├── test_fakes.py
│           ├── test_factories.py
│           ├── test_migrations.py
│           └── contracts/
│               ├── event_bus/
│               ├── llm/
│               └── kms/
├── services/
│   ├── api/
│   │   └── pyproject.toml (stub)
│   ├── triage_worker/
│   │   └── pyproject.toml (stub)
│   └── knowledge_worker/
│       └── pyproject.toml (stub)
├── apps/
│   ├── console/
│   │   └── package.json (stub)
│   └── widget/
│       └── package.json (stub)
├── ml/
│   └── evals/
│       ├── runner.py
│       ├── conftest.py
│       ├── golden/
│       │   ├── intents_v0.jsonl
│       │   └── conversations_v0.jsonl
│       └── tests/
│           └── test_eval_gates.py
├── tests/
│   ├── acceptance/
│   │   ├── features/
│   │   │   ├── j1_autonomous_wismo.feature
│   │   │   ├── j2_partial_autonomy_handoff.feature
│   │   │   ├── j3_escalation.feature
│   │   │   ├── f4_clarification.feature
│   │   │   ├── j5_admin_tuning.feature
│   │   │   └── j6_agent_correction.feature
│   │   └── conftest.py
│   └── contracts/
│       ├── event_bus/
│       ├── llm/
│       └── kms/
├── tools/
│   ├── docker-compose.yml
│   ├── litellm.yaml
│   └── postgres/
│       └── init.sql
└── Docs/
    ├── implementation-plan.md
    ├── triage-agent-product-and-technical-specification.md
    └── ai-powered-customer-support-triage-agent-solution-proposal.md
```

---

## Commit Order

Each commit leaves the codebase in a buildable, testable state. All commits include passing tests for the work.

### Commit 1: Monorepo Foundation
```
feat: establish uv + Turborepo monorepo with strict linting

- Root pyproject.toml with uv workspace members
- Ruff config (E, W, F, I, UP, SIM rules)
- mypy.ini with --strict mode
- TypeScript strict tsconfig
- turbo.json with lint, typecheck, test, build pipeline
- .pre-commit-config.yaml (Ruff, mypy, tsc, gitleaks)
- Makefile with smoke, lint, typecheck targets

Verification:
  make lint → pass
  make typecheck → pass
```

### Commit 2: Docker Compose Stack
```
feat: define local development stack

- docker-compose.yml with Postgres 18, Redis 7, MinIO, Mailpit, Langfuse, LiteLLM
- .env.example template
- tools/litellm.yaml for local testing
- tools/postgres/init.sql for pgvector extension + triage_app role

Verification:
  make up && make smoke → services ready
```

### Commit 3: CI Pipeline Skeleton
```
ci: add GitHub Actions workflow skeleton

- .github/workflows/ci.yml with 4-layer job structure (lint → unit → integration → eval-smoke)
- Composite actions for Python env setup and docker-compose orchestration
- Security scans (Gitleaks, Semgrep, Trivy)
- Caching for dependencies and build artifacts

Verification:
  Push to feature branch → CI runs all jobs (on empty stubs, lint/typecheck pass)
```

### Commit 4: py_core Foundational Modules
```
feat: add py_core package with tenant context, DB, errors, OTel, logging

- py_core/tenant.py with context var + SQLAlchemy SET LOCAL injection
- py_core/db.py with async session factory and FastAPI dependency
- py_core/errors.py with RFC 9457 ErrorResponse model and exception hierarchy
- py_core/otel.py with OpenTelemetry SDK setup
- py_core/logging.py with PII-free structlog configuration
- Unit tests (Tier A, strict TDD) with > 90% coverage

Verification:
  cd packages/py_core && make test → 20/20 tests pass
  Tenant context is mandatory; missing context fails closed
```

### Commit 5: Alembic Baseline Schema
```
feat: create baseline MVP database schema with RLS and indexes

- alembic/env.py with async support
- alembic/versions/0001_baseline_mvp_schema.py with all MVP tables
- Row-Level Security policies on all tenant-scoped tables
- HNSW indexes on embedding columns
- Composite primary keys and foreign keys
- Integration tests verifying RLS enforcement and index creation

Verification:
  cd packages/py_core && make migrate → migration 0001 applied
  pytest packages/py_core/tests/test_migrations.py -v → 7/7 tests pass
  Tenant A cannot read/write tenant B data
```

### Commit 6: Audit Hash-Chain Trigger
```
feat: add immutable audit log with hash-chain integrity

- alembic/versions/0002_audit_hash_chain_trigger.py with PL/pgSQL functions
- py_core/audit.py with verify_audit_chain() wrapper
- Hash-chain computation: sha256(prev_hash || tenant_id || actor_id || ...)
- BEFORE UPDATE/DELETE triggers that forbid modification
- Tests verifying chain integrity and immutability

Verification:
  pytest packages/py_core/tests/test_audit.py -v → 5/5 tests pass
  UPDATE/DELETE on audit_log by app role raises exception
```

### Commit 7: Test Kit — Fakes, Factories, Fixtures
```
feat: build test infrastructure with fakes, factories, and Testcontainers

- py_core/testing/fakes.py: FakeLLM, FakeClock, InMemoryEventBus
- py_core/testing/factories.py: factory_boy factories for domain models
- py_core/testing/cassette_recorder.py: VCR.py wrapper for HTTP replay
- tests/conftest.py with Testcontainers Postgres and Redis fixtures
- Unit tests verifying fake interfaces and factory uniqueness

Verification:
  pytest packages/py_core/tests/test_fakes.py -v → all pass
  Testcontainers fixtures start services and run migrations cleanly
```

### Commit 8: Eval Harness + Golden Datasets
```
feat: build evaluation framework and initial golden datasets

- ml/evals/runner.py with EvalRunner class for batch evaluation
- ml/evals/conftest.py with pytest integration and cassette mode
- ml/evals/golden/intents_v0.jsonl (300 rows, 12+ intents, all tenant scenarios)
- ml/evals/golden/conversations_v0.jsonl (20 journeys J1–J6 + edge cases)
- ml/evals/tests/test_eval_gates.py with baseline thresholds

Verification:
  pytest ml/evals/tests/test_eval_gates.py -v -m eval → conversations test passes, intents test fails (intentional baseline)
  Golden datasets are valid JSONL and load without errors
```

### Commit 9: MVP Acceptance Scenarios
```
feat: write MVP acceptance scenarios as pending pytest-bdd tests

- tests/acceptance/features/*.feature (Gherkin files for J1–J6, F4)
- tests/acceptance/conftest.py with step definitions all marked pytest.skip
- No executable behavior yet; steps are stubs

Verification:
  pytest tests/acceptance/ --collect-only → 40 steps collected
  pytest tests/acceptance/ -v → all tests marked SKIPPED
```

### Commit 10: Documentation & README
```
docs: add contributing guide and root README

- CONTRIBUTING.md with TDD tiers, Definition of Ready/Done, commit message format
- README.md with project overview, make target table, quick start
- Root README describes all 9 deliverables of Sprint 0

Verification:
  make lint → pass (README has no code to lint)
  all make targets are documented
```

---

## Verification Summary

After all 10 commits, run the full local and CI verification:

```bash
# Local full build
cd d:\WORKING\PORTFOLIO\FEATURED\ PROJECTS\Support-triage-agent-
make lint
make typecheck
make up
make test
make down

# Expected outcomes:
# - Ruff check: 0 violations
# - mypy: 0 errors
# - Docker compose: 6 services healthy
# - pytest: 50+ tests pass, >90% coverage on py_core
# - No test failures; 1 eval gate intentionally fails (baseline)
# - All acceptance tests marked SKIPPED (not ERROR)

# Push to main
git push origin feat/sprint-0-foundation

# CI should:
# 1. Lint + typecheck jobs pass in <2 min
# 2. Unit tests pass in <3 min
# 3. Integration tests pass in <10 min
# 4. Eval smoke passes with cassettes
# 5. Security scans complete (gitleaks, semgrep, trivy)
```

---

## Notes for the Coding Agent

- **Tenant context is mandatory.** Every database session must call `set_tenant()` first, or it raises `MissingTenantContext`. This fails closed and is verified in tests.
- **RLS is strict.** The `triage_app` role has NO `BYPASSRLS` and NO `SUPERUSER`. Tenant isolation is enforced at the Postgres layer, not the application layer.
- **Idempotency keys** are placeholder in Sprint 0; they become critical in Sprint 1 (ingestion) and Sprint 2 (actions).
- **Fakes must pass the same contract suites as real adapters.** This is why FakeLLM, FakeShopify, etc. are tested separately — they are the single source of truth for the interface.
- **Golden datasets are synthetic and have no real PII.** They are generated by Opus + human review and live in the repo.
- **All tests run locally in <60 s** (target for the optimized inner loop). Use `pytest -xvs` for debugging single tests.
- **No secrets in `.env.example`.** All values are placeholders or dummy keys; real secrets are passed at deployment time.

---

**End of Sprint 0 Plan**
