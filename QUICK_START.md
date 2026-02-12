# Quick Start Guide — Schreiber Foods Batch Inventory

This guide provides a quick overview of the implementation plans and how to use them.

## 📚 Documentation Overview

This repository now contains comprehensive implementation plans for the Schreiber Foods Batch Inventory & Shelf-Life Tracking system:

### 1. **IMPLEMENTATION_PLAN.md** (Primary Document)
The main implementation guide covering:
- Project structure and hexagonal architecture
- Complete data model design (Batch & ConsumptionRecord)
- All 6 REST API endpoint specifications
- Concurrency control strategy (pessimistic locking)
- Testing strategy and coverage goals
- Database migrations with Alembic
- 6-phase development roadmap
- Docker deployment configuration
- Technology stack and dependencies

**Start here** for the complete technical specification.

### 2. **DESIGN_NOTES.md**
In-depth analysis of the concurrency control approach:
- Problem statement and race condition scenarios
- Pessimistic locking implementation (SELECT FOR UPDATE)
- Rationale and trade-offs
- Alternative approaches considered
- Testing and validation strategy
- Performance characteristics

**Required deliverable** (200-400 words) explaining concurrency decisions.

### 3. **PROJECT_SCAFFOLD.md**
Ready-to-use code templates:
- Complete SQLModel models with business logic
- Repository layer with pessimistic locking
- Service layer for business operations
- Pydantic schemas for API contracts
- FastAPI endpoint implementations
- Custom exception classes
- Pytest fixtures and test examples
- Configuration files (pyproject.toml, .env)

**Use this** to accelerate implementation - copy/paste starting points for all major components.

### 4. **TESTING_STRATEGY.md**
Comprehensive testing approach:
- 50+ unit test specifications
- 30+ integration test cases
- Concurrency test scenarios (threads & multiprocessing)
- Coverage goals (90%+ target)
- CI/CD integration examples
- Test helper utilities

**Follow this** to achieve production-grade test coverage.

---

## 🚀 Implementation Roadmap

### Phase 1: Foundation (Week 1)
- Set up FastAPI project structure
- Configure PostgreSQL with SQLModel
- Create initial Alembic migrations
- Set up Docker Compose
- Configure pytest

### Phase 2: Core API (Week 2)
- Implement CRUD endpoints (POST, GET, DELETE)
- Create Pydantic schemas
- Add input validation
- Write integration tests

### Phase 3: Consumption & Concurrency (Week 3)
- Implement atomic consumption with SELECT FOR UPDATE
- Add business rule validations
- Write concurrency tests (threading + multiprocessing)
- Document concurrency approach

### Phase 4: Expiry Management (Week 3-4)
- Implement near-expiry query endpoint
- Optimize with database indexes
- Test with sample data

### Phase 5: Testing & Documentation (Week 4)
- Achieve 90%+ test coverage
- Finalize README.md
- Complete DESIGN_NOTES.md
- Test Docker deployment

### Phase 6: Optional Enhancements (If Time Permits)
- Pagination
- Structured logging
- Domain value objects
- Reserve-liters concept

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI 0.115+ | REST API |
| Database | PostgreSQL 16+ | Persistence |
| ORM | SQLModel 0.0.22+ | Database models |
| Migrations | Alembic 1.13+ | Schema versioning |
| Testing | Pytest 8.3+ | Test framework |
| Validation | Pydantic 2.9+ | Request/response schemas |
| Container | Docker 24+ | Deployment |

---

## 📋 Core Requirements Checklist

### REST Endpoints
- [ ] POST /api/batches — Create batch
- [ ] GET /api/batches — List active batches
- [ ] GET /api/batches/{id} — Get batch details
- [ ] POST /api/batches/{id}/consume — Consume liters
- [ ] GET /api/batches/near-expiry?n_days=N — Near-expiry query
- [ ] DELETE /api/batches/{id} — Soft delete

### Business Rules
- [ ] Expiry date = received_at + shelf_life_days (1-30 days)
- [ ] Batch code must match SCH-YYYYMMDD-XXXX pattern
- [ ] Batch code must be unique (409 on duplicate)
- [ ] Available liters = volume - sum(consumed)
- [ ] Consumption prevented when qty > available (409 Conflict)
- [ ] Consumption prevented on deleted batches (409 Conflict)
- [ ] Consumption prevented on expired batches (409 Conflict)
- [ ] Consumption operations are atomic and concurrency-safe

### Data Models
- [ ] Batch model with all required fields
- [ ] ConsumptionRecord model
- [ ] Soft delete support (deleted_at)
- [ ] Version column for concurrency control
- [ ] Proper indexes on key fields

### Testing
- [ ] Unit tests for domain logic (expiry, available liters)
- [ ] Integration tests for all endpoints
- [ ] Concurrency tests (thread-based simulation)
- [ ] Edge case tests (fractional liters, duplicate codes, deleted batches)
- [ ] 90%+ code coverage

### Deliverables
- [ ] Working code organized under app/
- [ ] Alembic migrations in alembic/
- [ ] README.md with setup instructions
- [ ] DESIGN_NOTES.md (concurrency approach)
- [ ] Passing test suite
- [ ] Docker Compose configuration

---

## 🔑 Key Design Decisions

### 1. Concurrency Control: Pessimistic Locking
**Decision**: Use `SELECT FOR UPDATE` to acquire exclusive row locks during consumption.

**Rationale**:
- Simplicity: No retry logic needed
- Correctness: Database-enforced mutual exclusion
- Performance: Acceptable for low-contention scenarios (batch operations are infrequent)

**Alternative Rejected**: Optimistic locking (version-based) - adds retry complexity for minimal benefit in this use case.

### 2. Architecture: Hexagonal (Ports & Adapters)
**Structure**:
```
API Layer (routers) → Domain Layer (services) → Repository Layer (database)
```

**Benefits**:
- Clear separation of concerns
- Testable business logic
- Framework-independent domain layer

### 3. Soft Delete
**Decision**: Use `deleted_at` timestamp instead of physical deletion.

**Rationale**:
- Audit trail preservation
- Compliance requirements (food safety tracking)
- Reversibility if needed

---

## 📊 Database Schema

### Batches Table
```sql
CREATE TABLE batches (
    id SERIAL PRIMARY KEY,
    batch_code VARCHAR(20) UNIQUE NOT NULL,  -- SCH-YYYYMMDD-XXXX
    received_at TIMESTAMP NOT NULL,
    shelf_life_days INT NOT NULL CHECK (shelf_life_days BETWEEN 1 AND 30),
    expiry_date TIMESTAMP NOT NULL,          -- Computed on creation
    volume_liters FLOAT NOT NULL CHECK (volume_liters >= 0),
    fat_percent FLOAT NOT NULL CHECK (fat_percent BETWEEN 0 AND 100),
    version INT NOT NULL DEFAULT 1,          -- Optimistic locking support
    deleted_at TIMESTAMP NULL,               -- Soft delete
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_batches_batch_code ON batches(batch_code);
CREATE INDEX idx_batches_expiry_date ON batches(expiry_date);
CREATE INDEX idx_batches_deleted_at ON batches(deleted_at);
```

### Consumption Records Table
```sql
CREATE TABLE consumption_records (
    id SERIAL PRIMARY KEY,
    batch_id INT NOT NULL REFERENCES batches(id),
    qty FLOAT NOT NULL CHECK (qty > 0),
    order_id VARCHAR(100) NULL,
    consumed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_consumption_batch_id ON consumption_records(batch_id);
CREATE INDEX idx_consumption_order_id ON consumption_records(order_id);
```

---

## 🧪 Testing Approach

### Unit Tests (~50 tests)
- Expiry date calculation
- Available liters computation
- Batch code validation
- Business rule enforcement

### Integration Tests (~30 tests)
- All API endpoints (happy path + error cases)
- Request/response validation
- Database transactions
- Soft delete behavior

### Concurrency Tests (~5 tests)
- Thread-based race condition simulation
- Process-based true parallelism
- Lost update prevention
- Atomic consumption verification

**Target Coverage**: 90%+ on domain and repository layers

---

## 📖 Usage Examples

### Creating a Batch
```bash
curl -X POST http://localhost:8000/api/batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_code": "SCH-20251204-0001",
    "received_at": "2025-12-04T08:30:00Z",
    "shelf_life_days": 7,
    "volume_liters": 1000.0,
    "fat_percent": 3.5
  }'
```

### Consuming from a Batch
```bash
curl -X POST http://localhost:8000/api/batches/1/consume \
  -H "Content-Type: application/json" \
  -d '{
    "qty": 250.0,
    "order_id": "ORDER-20251204-1234"
  }'
```

### Querying Near-Expiry Batches
```bash
curl http://localhost:8000/api/batches/near-expiry?n_days=3
```

---

## 🐳 Docker Quick Start

```bash
# Start services
docker-compose up --build

# Run migrations
docker-compose exec api alembic upgrade head

# Run tests
docker-compose exec api pytest

# View API docs
open http://localhost:8000/docs
```

---

## 📝 Next Steps

1. **Read IMPLEMENTATION_PLAN.md** for complete technical specification
2. **Review DESIGN_NOTES.md** to understand concurrency approach
3. **Use PROJECT_SCAFFOLD.md** templates to start coding
4. **Follow TESTING_STRATEGY.md** for test development
5. **Refer to this guide** for quick reference during implementation

---

## 🤔 Questions & Decisions

### Open Questions for Implementation
1. **Error Response Format**: Use RFC 7807 Problem Details or custom format?
2. **Logging Strategy**: JSON structured logs or plain text?
3. **API Versioning**: URL path (/v1/) or header-based?
4. **Authentication**: Out of scope for MVP? (Assume internal network)

### Recommended Decisions
- Use FastAPI's default error format (consistent with framework)
- Start with simple logging, add structure later
- Use URL path versioning (/api/batches) - simpler for MVP
- No authentication for MVP (document as production requirement)

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLModel Documentation](https://sqlmodel.tiangino.com/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [PostgreSQL SELECT FOR UPDATE](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)
- [Pytest Documentation](https://docs.pytest.org/)

---

**Implementation Time Estimate**: 3-4 weeks for complete MVP with tests and documentation

**Team Size Recommendation**: 1-2 developers

**Complexity Level**: Intermediate (requires understanding of concurrency, transactions, and API design)
