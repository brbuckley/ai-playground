# Schreiber Foods Batch Inventory System

A production-ready REST API for tracking milk batch inventory with atomic consumption operations, expiry management, and full audit trails.

## Architecture

Hexagonal architecture with clear separation of concerns:

```
HTTP Request → API Router → Domain Service → Repository → Database
```

- **API Layer** (`app/api/`): FastAPI routers handling HTTP concerns
- **Domain Layer** (`app/domain/`): Business logic and SQLModel models
- **Repository Layer** (`app/repositories/`): Database access abstraction

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Docker & Docker Compose (optional)

### Option 1: Docker Compose (Recommended)

```bash
# Start PostgreSQL and API
docker-compose up --build

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Option 2: Local Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 4. Start PostgreSQL
docker-compose up -d postgres

# 5. Run migrations
alembic upgrade head

# 6. Start API server
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/batches/` | Create a new batch |
| GET | `/api/batches/` | List active batches |
| GET | `/api/batches/{id}` | Get batch details |
| POST | `/api/batches/{id}/consume` | Consume from batch (atomic) |
| DELETE | `/api/batches/{id}` | Soft-delete a batch |
| GET | `/api/batches/near-expiry` | Get batches nearing expiry |

Interactive docs: http://localhost:8000/docs

## Running Tests

```bash
# All tests (unit + integration, uses SQLite in-memory)
pytest

# With coverage report
pytest --cov=app --cov-report=html

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Concurrency tests (requires PostgreSQL)
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/schreiber_test_db pytest tests/concurrency/
```

## Database Migrations

```bash
# Apply migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback one migration
alembic downgrade -1
```

## Concurrency Stress Test

```bash
# Requires running API server
python scripts/simulate_concurrent_ops.py
```

## Environment Variables

See `.env.example` for all configuration options.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection URL |
| `TEST_DATABASE_URL` | — | Test database URL |
| `API_PORT` | `8000` | API server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DEBUG` | `false` | Enable SQL echo |
