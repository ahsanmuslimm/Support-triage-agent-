# AI-Powered Customer Support Triage Agent

An intelligent system that automatically triages customer support requests, resolving simple queries autonomously while escalating complex issues to human agents.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- Docker and Docker Compose
- Node 20+ (for TypeScript apps)

### Local Development Setup

```bash
# Install dependencies
uv sync

# Start local services (Postgres, Redis, MinIO, etc.)
make up

# Run tests
make test

# Stop services
make down
```

## Make Targets

| Target | Description | Example |
|--------|-------------|---------|
| `make up` | Start local development stack | `docker-compose -f tools/docker-compose.yml up -d` |
| `make down` | Stop local development stack | Shuts down all services |
| `make smoke` | Run linting and type checking | Quick smoke test |
| `make test` | Run all unit and integration tests | Uses pytest |
| `make lint` | Run Ruff linter with auto-fix | `ruff check . --fix` |
| `make typecheck` | Run mypy with strict mode | Full type validation |
| `make migrate` | Run Alembic database migrations | Upgrades schema to latest version |
| `make seed` | Seed test data into database | Populates fixtures |

## Architecture

**Stack:**
- **Backend:** Python 3.12 + FastAPI, SQLAlchemy with async/await
- **Database:** PostgreSQL 18 with pgvector, Row-Level Security (RLS)
- **Cache:** Redis 7
- **Message Queue:** Temporal (for long-running workflows)
- **LLM Access:** LiteLLM proxy (unified routing + fallbacks)
- **Observability:** OpenTelemetry + Langfuse tracing
- **Frontend:** Next.js (admin console), Preact (chat widget)

**Monorepo Structure:**
- `packages/py_core` — Shared Python library (tenant context, DB, errors, logging, tests)
- `services/api` — FastAPI application (ingestion, classification, responses)
- `services/triage_worker` — LangGraph async worker (triage logic)
- `services/knowledge_worker` — Knowledge indexing and retrieval
- `apps/console` — Next.js admin dashboard
- `apps/widget` — Preact web chat widget
- `ml/evals` — Evaluation harness and golden datasets

## Development Workflow

See [CONTRIBUTING.md](./CONTRIBUTING.md) for:
- TDD discipline and test tier definitions
- Definition of Ready/Done
- Commit message format (Conventional Commits)
- Branch naming conventions

## Project Documentation

- [Implementation Plan](./docs/implementation-plan.md) — Detailed sprint roadmap
- [Product & Tech Spec](./docs/triage-agent-product-and-technical-specification.md)
- [Solution Proposal](./docs/ai-powered-customer-support-triage-agent-solution-proposal.md)

## License

Proprietary — All rights reserved.
