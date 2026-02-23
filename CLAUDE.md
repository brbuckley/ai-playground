# CLAUDE.md

This file provides guidance to Claude Code and AI agents working in this repository.

## Repository Overview

`ai-playground` is a monorepo for experimental projects. Current projects:

- `schreiber-batch-inventory/` — FastAPI batch inventory & shelf-life tracking system (hexagonal architecture, PostgreSQL, SQLModel, Alembic)

## QA: Required Before Every Commit

**AI agents MUST run all of the following QA checks and ensure they pass before committing any code.** Fix all failures before committing.

```bash
cd schreiber-batch-inventory

# Format check
uv run ruff format --check .

# Lint check
uv run ruff check .

# Type check
uv run ty check app/

# Unit + integration tests (requires running Postgres; skip in CI without DB)
uv run pytest tests/unit
```

> For integration and concurrency tests, a running PostgreSQL instance is required (see `docker-compose.yml`). In environments without Docker, run unit tests only: `uv run pytest tests/unit`.

If any check fails, fix the issues and re-run before committing.

## Development Setup

```bash
cd schreiber-batch-inventory

# Install dependencies (including dev extras)
uv sync --extra dev

# Start services
docker-compose up -d

# Run all tests
uv run pytest tests/
```

## Coding Conventions

- **Architecture:** Hexagonal (ports & adapters). Keep domain logic in `app/domain/`, infrastructure in `app/repositories/`, HTTP in `app/api/`.
- **Formatter/Linter:** `ruff` (line length 100, target Python 3.12).
- **Type checker:** `ty` (Astral).
- **Tests:** `pytest`. Unit tests in `tests/unit/`, integration in `tests/integration/`, concurrency in `tests/concurrency/`.
- **Migrations:** Always use Alembic. Never use `SQLModel.metadata.create_all()` in production code.
- **Soft deletes:** Use `deleted_at` timestamp; never hard-delete records.
- **Optimistic locking:** Use the `version` column for concurrent update protection.
