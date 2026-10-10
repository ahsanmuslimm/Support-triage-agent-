# Contributing to Triage Agent

## TDD Discipline: Test Tiers

All work follows Test-Driven Development (TDD) with five tiers:

- **Tier A (Strict TDD):** Write tests first, then code. Coverage ≥ 90% required. Examples: tenant context, database layer, error handling, audit chain.
- **Tier B (Behavioral Tests):** Write tests during implementation. Coverage ≥ 80% required. Examples: API endpoints, orchestration logic.
- **Tier C (Eval/Probe Tests):** Write tests after implementation. Verify metric gates. Examples: LLM classification, intent detection, response quality.
- **Tier D (Scenario Tests):** BDD scenarios written as pending tests (using `@pytest.mark.skip`). Define contracts for future sprints. Examples: acceptance scenarios, integration journeys.
- **Tier E (Manual):** User stories that require manual testing or don't fit automated testing. Examples: UI feedback, end-to-end flows in staging.

## Definition of Ready

A story is ready for implementation when it includes:
- Clear acceptance criteria
- Assigned tier (A–E)
- Any mocks, fakes, or test fixtures needed
- Known dependencies or blockers
- Expected test coverage %

## Definition of Done

A story is done when:
- ✅ Code passes pre-commit hooks (`ruff check`, `mypy --strict`, `gitleaks`)
- ✅ `make lint` and `make typecheck` both pass
- ✅ All tests pass: `make test`
- ✅ Coverage meets tier minimum
- ✅ Feature branch is pushed and a pull request is created
- ✅ All GitHub Actions CI jobs pass
- ✅ Code review approved by at least one team member

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type:** `feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `style`  
**Scope:** (optional) affected component: `tenant`, `db`, `api`, `classification`, etc.  
**Subject:** Imperative present tense; "add", not "added" or "adds"

### Examples:
```
feat(tenant): add context var isolation for async tasks

fix(errors): handle missing tenant with 403 response

test(audit): verify hash chain integrity after mutation

docs: add CONTRIBUTING.md guide

chore: update dependencies for Python 3.12
```

## Branch Naming

- Feature: `feat/<story-name>` (e.g., `feat/sprint-0-foundation`)
- Bug fix: `fix/<bug-name>` (e.g., `fix/tenant-isolation-race`)
- Chore: `chore/<task-name>` (e.g., `chore/upgrade-pytest`)

## Pull Request Process

1. Create a new branch: `git checkout -b feat/my-feature`
2. Make changes, commit with conventional messages
3. Run full verification locally: `make lint && make typecheck && make test`
4. Push to remote: `git push -u origin feat/my-feature`
5. Create PR with a description explaining the changes and what was tested
6. Address review feedback, then rebase/merge when approved

## Running Tests

### Unit tests (fast)
```bash
pytest packages/py_core/tests -m unit -v
```

### Integration tests (requires docker-compose up)
```bash
make up
pytest packages/py_core/tests -m integration -v
make down
```

### All tests
```bash
make test
```

### Single test with debugging
```bash
pytest packages/py_core/tests/test_tenant.py::test_get_tenant_not_set_raises_error -xvs
```

## Local Development Workflow

```bash
# 1. Start services
make up

# 2. Make code changes
# Edit files...

# 3. Run checks before commit
make lint      # Auto-fixes ruff violations
make typecheck # Strict type checking
make test      # Unit + integration tests

# 4. Commit and push
git add <files>
git commit -m "feat(scope): description"
git push -u origin feat/my-feature

# 5. Stop services when done
make down
```

## Code Style

- **Python:** Follows Ruff style guide (E, W, F, I, UP, SIM, etc.). Line length 100 chars.
- **TypeScript:** Follows tsconfig strict mode. Target ES2022.
- **Imports:** Use explicit imports; no star imports in production code.
- **Naming:** PEP 8 for Python, camelCase for TypeScript.

## Questions?

Post in the team Slack or check existing issues for answers.
