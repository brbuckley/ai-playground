# Workstream 3 — Background Agent Research Probe

## Overview

This probe explores **background agents as a runtime and execution concept**, aligned with the AI-Native SDLC research program.

The goal was not automation or orchestration, but to observe how AI agents behave when executing work asynchronously with minimal human supervision.

The subject of the probe is a real, working project: **Schreiber Foods Batch Inventory & Shelf-Life Tracking API** — a production-grade REST API built from scratch using Claude as the primary implementation agent.

---

## AI-Native SDLC Context

The emerging AI-Native SDLC introduces two execution models:

**Human–Agent Collaborative Coding**
- Engineers lead execution
- AI assists inside IDE/CLI (e.g. Cursor, Claude Code)
- Human stays in the loop at every step

**Autonomous Background Agents**
- Asynchronous execution — agent works while human does other things
- Strictly scoped tasks via GitHub issues
- Humans remain accountable for outcomes

This probe focuses on the second model: autonomous background execution via the Claude GitHub integration.

---

## The Demo Project

The agent built a functional **batch inventory REST API** for Schreiber Foods — tracking milk batch deliveries, shelf-life, and concurrent consumption operations.

### What Was Built

| Metric | Value |
| ----------------------- | ------------------------------------ |
| Python files | 32 |
| Source lines of code | ~1,200 (app layer) |
| Test lines of code | ~1,020 (unit + integration + e2e) |
| Total Python code | ~2,220 lines |
| REST API endpoints | 6 |
| Test suites | 4 (unit, integration, concurrency, e2e) |
| Database migrations | 1 (Alembic) |
| CI pipeline steps | 5 (format, lint, type-check, test, teardown) |
| Development span | ~10 days (Feb 12 – Feb 23, 2026) |
| Issues resolved by agent | 8 of 10 |

### API Endpoints Delivered

```
POST   /api/batches                 — Create a new batch
GET    /api/batches                 — List active batches
GET    /api/batches/{id}            — Retrieve batch details
POST   /api/batches/{id}/consume    — Consume volume (atomic, concurrency-safe)
GET    /api/batches/near-expiry     — Query batches nearing expiry
DELETE /api/batches/{id}            — Soft-delete a batch
```

### Architecture

The project follows **hexagonal architecture** (ports & adapters):

```
HTTP Request → API Router → Domain Service → Repository → PostgreSQL
```

- `app/api/` — thin FastAPI routers, HTTP concerns only
- `app/domain/` — pure business logic, framework-independent
- `app/repositories/` — data access layer (pessimistic locking for concurrency)

### Technology Stack

| Component | Technology |
| -------------- | ---------------------- |
| Framework | FastAPI 0.115+ |
| Database | PostgreSQL 16+ |
| ORM | SQLModel 0.0.22+ |
| Migrations | Alembic 1.13+ |
| Testing | Pytest 8.3+ |
| Validation | Pydantic 2.9+ |
| Package manager | uv |
| Linter/formatter | ruff |
| Type checker | ty (Astral) |
| Container | Docker + Compose |

---

## Tools Used in This Probe

| Tool | Role |
| -------------------- | ----------------------------------- |
| Claude GitHub Plugin | Autonomous coding agent |
| CodeRabbit | QA / review agent |
| GitHub Actions | CI execution |
| Human engineer | Scope definition + final validation |

### Claude (GitHub Integration)

- Reads GitHub issues and repository context
- Creates plans, implements features, and opens PRs
- Executes work asynchronously (background mode)
- Behaves similarly to a junior/mid-level engineer when scope is clear

### CodeRabbit (QA Agent)

- Performs PR code review automatically on each PR opened by Claude
- Suggests improvements and flags risk areas
- Helps maintain code consistency and quality signal

### GitHub Actions CI

Runs on every PR targeting `main`, scoped to `schreiber-batch-inventory/**`:

1. Install dependencies (`uv sync`)
2. Start PostgreSQL via Docker Compose
3. Format check (`ruff format --check`)
4. Lint (`ruff check`)
5. Type check (`ty check app/`)
6. Run full test suite (`pytest tests/ -v`)

---

## Execution Flow (Per Issue)

```
Human creates GitHub issue
        ↓
Issue assigned to @claude
        ↓
Claude reads issue + repo context
        ↓
Claude implements changes in a new branch
        ↓
PR opened automatically
        ↓
CodeRabbit performs automated review
        ↓
CI pipeline runs (lint → type-check → tests)
        ↓
Human performs final evaluation + merges
```

This intentionally removes humans from the execution loop to observe agent autonomy behavior.

---

## Development Process (Observed Run)

| Issue | Description | Agent vs Human |
| ------- | --------------------------------------- | -------------------------------- |
| #1 | Create extensive implementation plan | Claude |
| #2 | Phase 1 — project scaffolding | Claude + manual CI/QA additions |
| #3 | Phase 2 — domain models | Claude |
| #4 | Phase 3 — consumption & concurrency | Claude |
| #5 | Phase 4 — expiry management | Claude |
| #6 | Phase 5 — testing & documentation | Claude |
| #7 | E2E tests | Mostly human (with AI speed assist) |
| #8–#9 | Bug fixes and refinements | Claude |
| #10 | SDLC documentation (this file) | Claude |

**Manual additions by human:**
- QA tooling setup (ruff, ty configuration)
- GitHub Actions CI workflow
- `docker-compose` fix (commit `01b90ff`)
- E2E test scenarios (Issue #7 — used to stabilize integration behavior)

---

## Key Insights

### 1. Background agents are advancing rapidly

Claude completed small-to-medium complexity tasks **fully unsupervised** — from reading a GitHub issue to opening a functional PR with passing tests. No interactive prompting required.

### 2. Quality does not emerge automatically

The agent produced functional code, but production-grade quality required:

- CI automation (format, lint, type-check gates)
- QA agent (CodeRabbit) to catch style and logic issues
- A human-written E2E test suite to stabilize end-to-end behavior
- Manual review before merge

The 46% test-to-code ratio (1,020 test lines out of 2,220 total) reflects deliberate investment in quality infrastructure — not something the agent drove on its own.

### 3. Clear scope = strong performance

Claude received a detailed `IMPLEMENTATION_PLAN.md` (1,313 lines) up front. This investment in explicit specification paid off: the agent delivered a working API across 6 phases with minimal drift.

> Scope document quality directly determines agent output quality.

### 4. Execution feels like delegating to a real developer

Assigning an issue to Claude felt similar to delegating to a teammate:

- Agent plans first, then implements incrementally
- Async collaboration through PRs (not synchronous back-and-forth)
- Review and merge as the human control point

The main difference: no clarifying questions. The agent works with what it has, which makes upfront scope definition critical.

### 5. Speed improvement was significant

A full API with hexagonal architecture, pessimistic locking, and a multi-layer test suite was delivered in ~10 days — significantly faster than implementing manually, even with interactive AI assistance.

---

## Observations About Background Agents

- Agents follow instructions well when scope is **explicit and structured**.
- Missing guardrails (CI, QA tooling) lead to drift and minor assumptions.
- QA agents (CodeRabbit) improve signal but do not replace human judgment.
- **Testing is the primary control mechanism** — E2E tests were essential to catching integration issues.
- The agent produces code that compiles and passes tests, but human review is still needed for architectural decisions.

---

## Main Takeaway

Background agents are becoming viable participants in the SDLC.

> **Autonomy requires structure.**

Quality and safety depend on:

- Explicit work definition (detailed issues + planning docs)
- A layered testing strategy (unit → integration → e2e)
- Automated QA tooling (CI, linters, type checkers, review agents)
- Human accountability at review and merge time

This probe validates autonomous execution as a realistic SDLC capability. The next phase should focus on governance patterns, multi-agent orchestration, and longer-horizon task delegation.

---

## Repository Structure

```
ai-playground/
├── schreiber-batch-inventory/       # The demo project
│   ├── app/
│   │   ├── api/v1/batches.py        # 6 REST endpoints (161 lines)
│   │   ├── domain/
│   │   │   ├── models.py            # Batch + ConsumptionRecord (193 lines)
│   │   │   ├── services/            # Business logic layer
│   │   │   └── exceptions.py        # Domain error types (53 lines)
│   │   ├── repositories/
│   │   │   └── batch_repository.py  # DB layer + pessimistic locking (210 lines)
│   │   └── schemas/                 # Pydantic request/response schemas
│   ├── tests/
│   │   ├── unit/                    # Domain logic tests (196 lines)
│   │   ├── integration/             # API tests (278 lines)
│   │   ├── concurrency/             # Race condition tests (148 lines)
│   │   └── e2e/                     # End-to-end flows (356 lines)
│   ├── alembic/                     # Database migrations
│   ├── docker/                      # Dockerfile
│   └── docker-compose.yml
├── IMPLEMENTATION_PLAN.md           # Claude's initial plan (Issue #1)
├── DESIGN_NOTES.md                  # Concurrency design rationale
├── PROJECT_SCAFFOLD.md              # Code templates used by agent
├── TESTING_STRATEGY.md              # Test specification doc
└── DOCUMENTATION.md                 # This file (Issue #10)
```

---

*Generated with [Claude Code](https://claude.ai/code) — Workstream 3, AI-Native SDLC Research Program*
