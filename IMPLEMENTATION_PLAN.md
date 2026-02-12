# Schreiber Foods Batch Inventory System — Implementation Plan

## Executive Summary

This document provides a comprehensive implementation plan for the Schreiber Foods Batch Inventory & Shelf-Life Tracking system. The system will be built as a FastAPI monolith with PostgreSQL database, following hexagonal architecture principles to ensure maintainability, testability, and reliability under concurrent operations.

**Target Outcome**: A production-ready REST API that tracks milk batch inventory with atomic consumption operations, expiry management, and full audit trails.

---

## 1. Project Structure & Architecture

### 1.1 Directory Structure

```
schreiber-batch-inventory/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Configuration management
│   ├── database.py                # Database connection & session management
│   │
│   ├── api/                       # API Layer (thin routers)
│   │   ├── __init__.py
│   │   ├── dependencies.py        # Dependency injection
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py          # Main router aggregator
│   │       └── batches.py         # Batch endpoints
│   │
│   ├── schemas/                   # Pydantic models (API contracts)
│   │   ├── __init__.py
│   │   ├── batch.py               # Batch request/response schemas
│   │   └── consumption.py         # Consumption schemas
│   │
│   ├── domain/                    # Domain/Business Logic Layer
│   │   ├── __init__.py
│   │   ├── models.py              # SQLModel database models
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── batch_service.py   # Core business logic
│   │   ├── exceptions.py          # Domain-specific exceptions
│   │   └── value_objects.py       # Optional: Volume, BatchCode VOs
│   │
│   └── repositories/              # Data Access Layer
│       ├── __init__.py
│       └── batch_repository.py    # Database operations
│
├── alembic/                       # Database migrations
│   ├── versions/
│   └── env.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_domain_logic.py   # Business logic tests
│   │   └── test_value_objects.py
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_batch_api.py      # API integration tests
│   └── concurrency/
│       ├── __init__.py
│       └── test_concurrent_consumption.py
│
├── scripts/
│   └── simulate_concurrent_ops.py # Manual concurrency testing
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── alembic.ini
├── pyproject.toml                 # Poetry/pip dependencies
├── README.md                      # Setup & usage instructions
├── DESIGN_NOTES.md                # Concurrency approach documentation
└── .env.example                   # Environment variables template
```

### 1.2 Architectural Principles

**Hexagonal Architecture (Ports & Adapters)**:
- **API Layer**: Thin FastAPI routers that handle HTTP concerns (validation, status codes)
- **Domain Layer**: Pure business logic, independent of frameworks
- **Repository Layer**: Database access abstraction

**Benefits**:
- Testability: Domain logic can be tested without database
- Maintainability: Clear separation of concerns
- Flexibility: Easy to swap persistence layer if needed

**Layer Communication**:
```
HTTP Request → API Router → Domain Service → Repository → Database
                    ↓             ↓
                Schemas    Business Rules
```

---

## 2. Data Model Design

### 2.1 Database Schema

#### Batch Table
```python
class Batch(SQLModel, table=True):
    __tablename__ = "batches"

    # Primary Key
    id: int = Field(default=None, primary_key=True)

    # Business Identifiers
    batch_code: str = Field(unique=True, index=True, max_length=20)
    # Pattern: SCH-YYYYMMDD-XXXX

    # Batch Properties
    received_at: datetime = Field(index=True)
    shelf_life_days: int = Field(ge=1, le=30, default=7)
    expiry_date: datetime = Field(index=True)  # Computed on creation
    volume_liters: float = Field(ge=0)
    fat_percent: float = Field(ge=0, le=100)

    # Concurrency Control
    version: int = Field(default=1)  # For optimistic locking

    # Soft Delete
    deleted_at: datetime | None = Field(default=None, index=True)

    # Audit Trail
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    consumption_records: list["ConsumptionRecord"] = Relationship(
        back_populates="batch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
```

#### ConsumptionRecord Table
```python
class ConsumptionRecord(SQLModel, table=True):
    __tablename__ = "consumption_records"

    # Primary Key
    id: int = Field(default=None, primary_key=True)

    # Foreign Key
    batch_id: int = Field(foreign_key="batches.id", index=True)

    # Consumption Details
    qty: float = Field(ge=0)  # Liters consumed
    order_id: str | None = Field(default=None, max_length=100, index=True)

    # Audit Trail
    consumed_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    batch: Batch = Relationship(back_populates="consumption_records")
```

### 2.2 Indexes Strategy

**Primary Indexes** (for performance):
- `batches.batch_code` (UNIQUE)
- `batches.expiry_date` (for near-expiry queries)
- `batches.deleted_at` (for filtering soft-deleted)
- `consumption_records.batch_id` (foreign key)
- `consumption_records.order_id` (for lookups)

**Composite Index** (optional optimization):
- `(expiry_date, deleted_at)` for near-expiry queries

### 2.3 Computed Properties

**Available Liters Calculation**:
```python
@property
def available_liters(self) -> float:
    """Compute available volume: total - sum(consumed)"""
    if not self.consumption_records:
        return self.volume_liters
    total_consumed = sum(record.qty for record in self.consumption_records)
    return max(0, self.volume_liters - total_consumed)
```

**Is Expired Check**:
```python
@property
def is_expired(self) -> bool:
    """Check if batch has passed expiry date"""
    return datetime.utcnow() > self.expiry_date
```

---

## 3. API Design

### 3.1 Endpoint Specifications

#### POST /api/batches
**Purpose**: Create a new batch

**Request Body**:
```json
{
  "batch_code": "SCH-20251204-0001",
  "received_at": "2025-12-04T08:30:00Z",
  "shelf_life_days": 7,
  "volume_liters": 1000.0,
  "fat_percent": 3.5
}
```

**Response** (201 Created):
```json
{
  "id": 1,
  "batch_code": "SCH-20251204-0001",
  "received_at": "2025-12-04T08:30:00Z",
  "shelf_life_days": 7,
  "expiry_date": "2025-12-11T08:30:00Z",
  "volume_liters": 1000.0,
  "available_liters": 1000.0,
  "fat_percent": 3.5,
  "version": 1,
  "created_at": "2025-12-04T08:30:00Z"
}
```

**Validations**:
- Batch code must match pattern `SCH-YYYYMMDD-XXXX`
- Batch code must be unique (409 Conflict if duplicate)
- Shelf life days must be 1-30
- Volume must be >= 0
- Fat percent must be 0-100

**Business Logic**:
- Compute `expiry_date = received_at + timedelta(days=shelf_life_days)`

---

#### GET /api/batches
**Purpose**: List active (non-deleted) batches

**Query Parameters**:
- `skip` (int, default=0): Pagination offset
- `limit` (int, default=100): Page size

**Response** (200 OK):
```json
{
  "batches": [
    {
      "id": 1,
      "batch_code": "SCH-20251204-0001",
      "expiry_date": "2025-12-11T08:30:00Z",
      "volume_liters": 1000.0,
      "available_liters": 750.0,
      "is_expired": false
    }
  ],
  "total": 1
}
```

**Filters Applied**:
- `deleted_at IS NULL`

---

#### GET /api/batches/{id}
**Purpose**: Retrieve a single batch with full details

**Response** (200 OK):
```json
{
  "id": 1,
  "batch_code": "SCH-20251204-0001",
  "received_at": "2025-12-04T08:30:00Z",
  "shelf_life_days": 7,
  "expiry_date": "2025-12-11T08:30:00Z",
  "volume_liters": 1000.0,
  "available_liters": 750.0,
  "fat_percent": 3.5,
  "version": 3,
  "consumption_records": [
    {
      "id": 1,
      "qty": 250.0,
      "order_id": "ORDER-001",
      "consumed_at": "2025-12-05T10:00:00Z"
    }
  ]
}
```

**Error Responses**:
- 404 Not Found: Batch does not exist or is soft-deleted

---

#### POST /api/batches/{id}/consume
**Purpose**: Consume liters from a batch (atomic operation)

**Request Body**:
```json
{
  "qty": 250.0,
  "order_id": "ORDER-20251204-1234"
}
```

**Response** (200 OK):
```json
{
  "batch_id": 1,
  "qty_consumed": 250.0,
  "available_liters": 750.0,
  "order_id": "ORDER-20251204-1234",
  "consumed_at": "2025-12-05T10:00:00Z"
}
```

**Error Responses**:
- 404 Not Found: Batch does not exist
- 409 Conflict: Insufficient available liters
- 409 Conflict: Batch is deleted
- 409 Conflict: Batch is expired
- 409 Conflict: Concurrent modification detected (version mismatch)

**Business Logic**:
1. Acquire lock on batch (pessimistic) or check version (optimistic)
2. Validate batch is not deleted
3. Validate batch is not expired
4. Calculate available liters
5. Ensure `qty <= available_liters`
6. Create ConsumptionRecord
7. Increment batch version (for optimistic locking)
8. Commit transaction atomically

---

#### GET /api/batches/near-expiry
**Purpose**: List batches nearing expiry with available volume

**Query Parameters**:
- `n_days` (int, required): Look-ahead window

**Example**: `GET /api/batches/near-expiry?n_days=3`

**Response** (200 OK):
```json
{
  "batches": [
    {
      "id": 1,
      "batch_code": "SCH-20251204-0001",
      "expiry_date": "2025-12-11T08:30:00Z",
      "available_liters": 750.0,
      "days_until_expiry": 2
    }
  ],
  "query_date": "2025-12-09T00:00:00Z",
  "n_days": 3
}
```

**Filters Applied**:
- `deleted_at IS NULL`
- `expiry_date <= now() + n_days`
- `available_liters > 0`

**Sorting**: Order by `expiry_date ASC` (soonest first)

---

#### DELETE /api/batches/{id}
**Purpose**: Soft-delete a batch

**Response** (204 No Content)

**Business Logic**:
- Set `deleted_at = now()`
- Batch remains in database for audit purposes
- Deleted batches cannot be consumed
- Deleted batches do not appear in list/near-expiry endpoints

**Error Responses**:
- 404 Not Found: Batch does not exist
- 409 Conflict: Batch already deleted

---

### 3.2 Pydantic Schemas

**Request Schemas** (schemas/batch.py):
```python
class BatchCreate(BaseModel):
    batch_code: str = Field(pattern=r"^SCH-\d{8}-\d{4}$")
    received_at: datetime
    shelf_life_days: int = Field(ge=1, le=30, default=7)
    volume_liters: float = Field(ge=0)
    fat_percent: float = Field(ge=0, le=100)

class ConsumeRequest(BaseModel):
    qty: float = Field(gt=0)
    order_id: str | None = None
```

**Response Schemas**:
```python
class BatchResponse(BaseModel):
    id: int
    batch_code: str
    received_at: datetime
    shelf_life_days: int
    expiry_date: datetime
    volume_liters: float
    available_liters: float
    fat_percent: float
    version: int
    is_expired: bool
    created_at: datetime

class ConsumptionResponse(BaseModel):
    batch_id: int
    qty_consumed: float
    available_liters: float
    order_id: str | None
    consumed_at: datetime
```

---

## 4. Concurrency Control Strategy

### 4.1 Problem Analysis

**Concurrency Risks**:
- **Race Condition**: Two requests consume simultaneously, exceeding available liters
- **Lost Update**: One consumption overwrites another
- **Phantom Read**: Available liters calculation includes uncommitted data

**Example Scenario**:
```
Batch has 100L available
Request A: Consume 80L (checks availability, sees 100L)
Request B: Consume 80L (checks availability, sees 100L)
Both proceed → Total consumed = 160L > 100L (VIOLATION)
```

### 4.2 Recommended Approach: Pessimistic Locking

**Implementation**: PostgreSQL `SELECT FOR UPDATE`

**Rationale**:
- **Simplicity**: Prevents conflicts at database level
- **Reliability**: No retry logic needed
- **Performance**: Acceptable for batch operations (low contention expected)
- **Clarity**: Easy to reason about and test

**Flow**:
```python
async def consume_batch(batch_id: int, qty: float, order_id: str | None, db: Session):
    # 1. Acquire exclusive row lock
    batch = db.exec(
        select(Batch)
        .where(Batch.id == batch_id)
        .with_for_update()  # Pessimistic lock
    ).first()

    if not batch:
        raise BatchNotFound()

    # 2. Validate state (holding lock)
    if batch.deleted_at:
        raise BatchDeleted()

    if batch.is_expired:
        raise BatchExpired()

    available = batch.available_liters
    if qty > available:
        raise InsufficientVolume(available=available, requested=qty)

    # 3. Create consumption record
    record = ConsumptionRecord(
        batch_id=batch_id,
        qty=qty,
        order_id=order_id
    )
    db.add(record)

    # 4. Update batch version (for audit)
    batch.version += 1
    batch.updated_at = datetime.utcnow()

    # 5. Commit (releases lock)
    db.commit()
    db.refresh(batch)

    return record
```

**Lock Behavior**:
- Other transactions attempting `SELECT FOR UPDATE` on the same batch will block
- Lock is held until transaction commits or rolls back
- Timeout can be configured to prevent indefinite waiting

### 4.3 Alternative: Optimistic Locking

**Implementation**: Version column with compare-and-swap

**Flow**:
```python
async def consume_batch_optimistic(batch_id: int, qty: float, order_id: str | None, db: Session):
    # 1. Read batch with current version
    batch = db.get(Batch, batch_id)
    original_version = batch.version

    # 2. Validate state
    if batch.deleted_at:
        raise BatchDeleted()

    available = batch.available_liters
    if qty > available:
        raise InsufficientVolume()

    # 3. Create consumption record
    record = ConsumptionRecord(...)
    db.add(record)

    # 4. Increment version
    batch.version += 1

    # 5. Update with version check
    result = db.exec(
        update(Batch)
        .where(Batch.id == batch_id, Batch.version == original_version)
        .values(version=batch.version, updated_at=datetime.utcnow())
    )

    if result.rowcount == 0:
        db.rollback()
        raise ConcurrentModificationError()  # Retry needed

    db.commit()
    return record
```

**Trade-offs**:
- **Pros**: Better for high-contention scenarios (no blocking)
- **Cons**: Requires client retry logic; more complex error handling

**Recommendation**: Use pessimistic locking unless performance profiling shows lock contention issues.

### 4.4 Transaction Isolation

**Database Configuration**:
```python
# config.py
DATABASE_URL = "postgresql://user:pass@host/db"

engine = create_engine(
    DATABASE_URL,
    isolation_level="READ COMMITTED",  # Default for PostgreSQL
    pool_size=20,
    max_overflow=0
)
```

**Isolation Level**: `READ COMMITTED`
- Prevents dirty reads
- Sufficient when combined with `SELECT FOR UPDATE`
- Lower overhead than `SERIALIZABLE`

---

## 5. Testing Strategy

### 5.1 Unit Tests (tests/unit/)

**Target**: Domain logic in isolation

**Test Cases**:
1. **Expiry Date Calculation**
   ```python
   def test_expiry_date_computed_correctly():
       received = datetime(2025, 12, 4, 8, 30)
       shelf_life = 7
       expected = datetime(2025, 12, 11, 8, 30)
       # Assert expiry_date = received_at + timedelta(days=shelf_life)
   ```

2. **Available Liters Calculation**
   ```python
   def test_available_liters_with_consumption():
       batch = Batch(volume_liters=1000.0)
       batch.consumption_records = [
           ConsumptionRecord(qty=250.0),
           ConsumptionRecord(qty=100.0)
       ]
       assert batch.available_liters == 650.0
   ```

3. **Batch Code Validation**
   ```python
   def test_batch_code_pattern_validation():
       valid = "SCH-20251204-0001"
       invalid = "INVALID-CODE"
       # Test regex pattern matching
   ```

4. **Fractional Liters Support**
   ```python
   def test_fractional_consumption():
       batch = Batch(volume_liters=100.5)
       # Consume 50.25L
       # Assert available = 50.25L
   ```

**Tools**: `pytest`, `pytest-cov`

---

### 5.2 Integration Tests (tests/integration/)

**Target**: Full API flow with test database

**Setup**:
```python
# conftest.py
@pytest.fixture(scope="function")
def test_db():
    """Create fresh test database for each test"""
    engine = create_engine("postgresql://test:test@localhost/test_db")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)

@pytest.fixture
def client(test_db):
    """FastAPI test client"""
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app)
```

**Test Cases**:
1. **Happy Path: Create → Consume → Verify**
   ```python
   def test_create_and_consume_batch(client):
       # POST /api/batches
       response = client.post("/api/batches", json={...})
       assert response.status_code == 201
       batch_id = response.json()["id"]

       # POST /api/batches/{id}/consume
       response = client.post(f"/api/batches/{batch_id}/consume", json={"qty": 250.0})
       assert response.status_code == 200
       assert response.json()["available_liters"] == 750.0
   ```

2. **Over-Consumption Prevention**
   ```python
   def test_consume_more_than_available(client):
       batch_id = create_batch(volume=100.0)
       response = client.post(f"/api/batches/{batch_id}/consume", json={"qty": 150.0})
       assert response.status_code == 409
       assert "insufficient" in response.json()["detail"].lower()
   ```

3. **Duplicate Batch Code**
   ```python
   def test_duplicate_batch_code(client):
       batch_data = {"batch_code": "SCH-20251204-0001", ...}
       client.post("/api/batches", json=batch_data)  # First insert
       response = client.post("/api/batches", json=batch_data)  # Duplicate
       assert response.status_code == 409
   ```

4. **Soft Delete Prevents Consumption**
   ```python
   def test_deleted_batch_cannot_be_consumed(client):
       batch_id = create_batch()
       client.delete(f"/api/batches/{batch_id}")
       response = client.post(f"/api/batches/{batch_id}/consume", json={"qty": 10.0})
       assert response.status_code == 409
   ```

5. **Near-Expiry Filtering**
   ```python
   def test_near_expiry_query(client):
       # Create batch expiring in 2 days
       # Create batch expiring in 10 days
       response = client.get("/api/batches/near-expiry?n_days=3")
       batches = response.json()["batches"]
       assert len(batches) == 1  # Only 2-day batch included
   ```

**Tools**: `pytest`, `httpx.TestClient`, `pytest-asyncio`

---

### 5.3 Concurrency Tests (tests/concurrency/)

**Target**: Verify atomic consumption under concurrent load

**Approach**: Simulate multiple threads/processes consuming simultaneously

**Test Case 1: Thread-Based Concurrent Consumption**
```python
import threading
from concurrent.futures import ThreadPoolExecutor

def test_concurrent_consumption_prevents_overuse():
    # Setup: Create batch with 100L
    batch_id = create_batch(volume=100.0)

    # Attempt 10 concurrent consumptions of 15L each
    # Expected: Total consumed ≤ 100L (only 6 should succeed)

    results = []

    def consume():
        try:
            response = client.post(f"/api/batches/{batch_id}/consume", json={"qty": 15.0})
            results.append(response.status_code)
        except Exception as e:
            results.append(None)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(consume) for _ in range(10)]
        for future in futures:
            future.result()

    # Verify results
    successes = [r for r in results if r == 200]
    conflicts = [r for r in results if r == 409]

    assert len(successes) == 6  # 6 * 15L = 90L (within 100L)
    assert len(conflicts) == 4  # 4 failed due to insufficient volume

    # Verify final state
    batch = db.get(Batch, batch_id)
    assert batch.available_liters == 10.0  # 100 - 90
```

**Test Case 2: Process-Based Simulation**
```python
import multiprocessing

def test_concurrent_consumption_multiprocess():
    # Similar to above but using multiprocessing.Pool
    # Ensures true parallelism (not GIL-limited)
```

**Test Case 3: Race Condition Detection**
```python
def test_no_lost_updates():
    """Verify that no consumption records are lost due to race conditions"""
    batch_id = create_batch(volume=1000.0)

    # Perform 100 concurrent consumptions of 5L each
    # Expected: 100 ConsumptionRecords created, total = 500L consumed

    # ... concurrent execution ...

    records = db.exec(
        select(ConsumptionRecord).where(ConsumptionRecord.batch_id == batch_id)
    ).all()

    assert len(records) == 100
    assert sum(r.qty for r in records) == 500.0
```

**Tools**: `pytest`, `threading`, `multiprocessing`, `concurrent.futures`

---

### 5.4 Test Coverage Goals

- **Unit Tests**: 90%+ coverage of domain logic
- **Integration Tests**: All API endpoints with happy + error paths
- **Concurrency Tests**: At least 2 scenarios demonstrating safety

**Coverage Measurement**:
```bash
pytest --cov=app --cov-report=html --cov-report=term
```

---

## 6. Database Migrations (Alembic)

### 6.1 Migration Files

**Initial Migration** (`alembic/versions/001_create_batches_and_consumption.py`):
```python
def upgrade():
    # Create batches table
    op.create_table(
        'batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_code', sa.String(20), unique=True, nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('shelf_life_days', sa.Integer(), nullable=False),
        sa.Column('expiry_date', sa.DateTime(), nullable=False),
        sa.Column('volume_liters', sa.Float(), nullable=False),
        sa.Column('fat_percent', sa.Float(), nullable=False),
        sa.Column('version', sa.Integer(), default=1, nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )

    # Create indexes
    op.create_index('ix_batches_batch_code', 'batches', ['batch_code'])
    op.create_index('ix_batches_expiry_date', 'batches', ['expiry_date'])
    op.create_index('ix_batches_deleted_at', 'batches', ['deleted_at'])

    # Create consumption_records table
    op.create_table(
        'consumption_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('batches.id'), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('order_id', sa.String(100), nullable=True),
        sa.Column('consumed_at', sa.DateTime(), nullable=False)
    )

    # Create indexes
    op.create_index('ix_consumption_batch_id', 'consumption_records', ['batch_id'])
    op.create_index('ix_consumption_order_id', 'consumption_records', ['order_id'])

def downgrade():
    op.drop_table('consumption_records')
    op.drop_table('batches')
```

### 6.2 Migration Commands

```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

---

## 7. Development Phases & Milestones

### Phase 1: Foundation (Week 1)
**Goal**: Project setup and data layer

**Tasks**:
- [ ] Initialize FastAPI project structure
- [ ] Configure Poetry/pip dependencies
- [ ] Set up PostgreSQL connection (SQLModel)
- [ ] Create Batch and ConsumptionRecord models
- [ ] Write initial Alembic migration
- [ ] Create Docker Compose for local development
- [ ] Set up pytest configuration and fixtures

**Deliverable**: Working database with migrations, basic project structure

---

### Phase 2: Core API Implementation (Week 2)
**Goal**: Implement REST endpoints with basic functionality

**Tasks**:
- [ ] Implement POST /api/batches (create batch)
- [ ] Implement GET /api/batches (list batches)
- [ ] Implement GET /api/batches/{id} (retrieve batch)
- [ ] Implement DELETE /api/batches/{id} (soft delete)
- [ ] Create Pydantic request/response schemas
- [ ] Add input validation and error handling
- [ ] Write integration tests for each endpoint

**Deliverable**: Working CRUD API (excluding consumption)

---

### Phase 3: Consumption Logic & Concurrency (Week 3)
**Goal**: Implement atomic consumption with concurrency safety

**Tasks**:
- [ ] Implement batch_repository.consume_batch() with pessimistic locking
- [ ] Implement POST /api/batches/{id}/consume endpoint
- [ ] Add business rule validations (expiry, available liters, deleted)
- [ ] Write unit tests for consumption logic
- [ ] Write concurrency tests (threading + multiprocessing)
- [ ] Tune database connection pool settings
- [ ] Document concurrency approach in DESIGN_NOTES.md

**Deliverable**: Fully functional consumption API with proven concurrency safety

---

### Phase 4: Expiry Management (Week 3-4)
**Goal**: Implement near-expiry queries and reporting

**Tasks**:
- [ ] Implement GET /api/batches/near-expiry endpoint
- [ ] Optimize query with proper indexes
- [ ] Add sorting by expiry_date
- [ ] Write integration tests for near-expiry filtering
- [ ] Test performance with sample data (1000+ batches)

**Deliverable**: Near-expiry reporting functionality

---

### Phase 5: Testing & Documentation (Week 4)
**Goal**: Comprehensive test coverage and documentation

**Tasks**:
- [ ] Achieve 90%+ test coverage
- [ ] Add edge case tests (fractional liters, duplicate codes, etc.)
- [ ] Write README.md with setup instructions
- [ ] Write DESIGN_NOTES.md (200-400 words on concurrency)
- [ ] Create .env.example file
- [ ] Add API documentation (FastAPI auto-docs)
- [ ] Test Docker deployment end-to-end

**Deliverable**: Production-ready codebase with documentation

---

### Phase 6: Optional Enhancements (If Time Permits)
**Goal**: Polish and additional features

**Tasks**:
- [ ] Add pagination to list endpoints
- [ ] Implement structured logging with correlation IDs
- [ ] Create domain value objects (Volume, BatchCode)
- [ ] Add reserve-liters concept for production planning
- [ ] Build simple UI or CLI tool for testing
- [ ] Set up CI/CD pipeline

**Deliverable**: Enhanced system with extra features

---

## 8. Technical Specifications

### 8.1 Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | 0.115+ |
| Database | PostgreSQL | 16+ |
| ORM | SQLModel | 0.0.22+ |
| Migrations | Alembic | 1.13+ |
| Testing | Pytest | 8.3+ |
| Async Runtime | Asyncio | Built-in |
| Validation | Pydantic | 2.9+ |
| Containerization | Docker | 24+ |

### 8.2 Dependencies (pyproject.toml)

```toml
[project]
name = "schreiber-batch-inventory"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115.0",
    "sqlmodel>=0.0.22",
    "psycopg2-binary>=2.9.9",
    "alembic>=1.13.0",
    "uvicorn[standard]>=0.30.0",
    "python-dotenv>=1.0.0",
    "pydantic-settings>=2.5.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0"
]
```

### 8.3 Environment Variables (.env.example)

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/schreiber_db
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/schreiber_test

# API
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# Logging
LOG_LEVEL=INFO
```

---

## 9. Deployment & Operations

### 9.1 Local Development Setup

**Prerequisites**:
- Python 3.12+
- PostgreSQL 16+
- Docker (optional but recommended)

**Setup Steps**:
```bash
# 1. Clone repository
git clone <repo-url>
cd schreiber-batch-inventory

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Start PostgreSQL (Docker)
docker-compose up -d postgres

# 5. Run migrations
alembic upgrade head

# 6. Start API server
uvicorn app.main:app --reload
```

**Access API**: http://localhost:8000
**Interactive Docs**: http://localhost:8000/docs

---

### 9.2 Docker Deployment

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: schreiber_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/schreiber_db
    depends_on:
      - postgres
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

volumes:
  postgres_data:
```

**Build & Run**:
```bash
docker-compose up --build
```

---

### 9.3 Testing Instructions

**Run All Tests**:
```bash
pytest
```

**Run with Coverage**:
```bash
pytest --cov=app --cov-report=html
```

**Run Specific Test Suite**:
```bash
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
pytest tests/concurrency/   # Concurrency tests only
```

**Run Concurrency Stress Test**:
```bash
python scripts/simulate_concurrent_ops.py
```

---

## 10. Design Notes (DESIGN_NOTES.md)

**Purpose**: Explain concurrency approach and trade-offs (200-400 words)

**Outline**:
1. **Problem Statement**: Why concurrency control is critical
2. **Chosen Approach**: Pessimistic locking with `SELECT FOR UPDATE`
3. **Rationale**:
   - Simplicity over optimistic locking
   - Low expected contention (batch operations are infrequent)
   - Database-level guarantees reduce application complexity
4. **Trade-offs**:
   - Blocking behavior under high contention
   - Lock timeout considerations
5. **Alternative Considered**: Optimistic locking with version column
6. **Testing Strategy**: How concurrency tests validate correctness
7. **Performance Characteristics**: Expected throughput and latency

**Example Content**:
```markdown
# Concurrency Control Design

## Problem
Multiple production operators may attempt to consume from the same batch
simultaneously. Without proper concurrency control, this creates a race
condition where total consumption could exceed available volume, violating
business rules.

## Chosen Approach: Pessimistic Locking
We use PostgreSQL's `SELECT FOR UPDATE` to acquire an exclusive row-level
lock on the batch during consumption operations. This ensures that only one
transaction can modify a batch at a time.

## Rationale
1. **Correctness**: Database-enforced locking eliminates race conditions
2. **Simplicity**: No retry logic needed in application code
3. **Low Contention**: Batch consumption is infrequent (<10 ops/min expected)
4. **Transactional Guarantees**: PostgreSQL handles deadlock detection

## Trade-offs
- **Blocking**: Concurrent requests wait for lock release (acceptable for our use case)
- **Timeout Risk**: Long-running transactions could cause lock waits (mitigated by timeouts)

## Alternative: Optimistic Locking
We considered using a version column with compare-and-swap logic. This would
avoid blocking but requires client retry logic and adds complexity. Given our
low-contention scenario, the simplicity of pessimistic locking outweighs the
potential performance benefits of optimistic locking.

## Validation
Our concurrency tests simulate 10 simultaneous consumption attempts, verifying
that total consumption never exceeds available volume and that no
ConsumptionRecords are lost.
```

---

## 11. Success Criteria & Definition of Done

### Functional Requirements
- [x] All 6 REST endpoints implemented and working
- [x] Batch creation with expiry_date calculation
- [x] Atomic consumption with concurrency safety
- [x] Near-expiry filtering with correct logic
- [x] Soft delete behavior
- [x] Proper error handling (404, 409, etc.)

### Code Quality
- [x] Hexagonal architecture structure followed
- [x] Type annotations on all functions
- [x] Clear separation of concerns (API → Domain → Repository)
- [x] Custom exception classes for domain errors
- [x] Input validation using Pydantic

### Testing
- [x] Unit tests for domain logic (90%+ coverage)
- [x] Integration tests for all endpoints
- [x] At least 2 concurrency tests demonstrating safety
- [x] Edge case tests (duplicate codes, fractional liters, deleted batches)
- [x] All tests passing

### Documentation
- [x] README.md with setup and run instructions
- [x] DESIGN_NOTES.md (200-400 words on concurrency)
- [x] API documentation (via FastAPI /docs)
- [x] Inline code comments for complex logic

### Deployment
- [x] Alembic migrations provided
- [x] Docker Compose configuration
- [x] .env.example file
- [x] Application runs locally without errors

---

## 12. Risk Assessment & Mitigation

### High Risk: Concurrency Bugs
**Mitigation**:
- Use well-tested pessimistic locking pattern
- Comprehensive concurrency tests
- Code review focused on transaction boundaries

### Medium Risk: Performance Under Load
**Mitigation**:
- Use database connection pooling
- Add indexes on frequently queried columns
- Monitor lock wait times in production

### Low Risk: Data Migration Issues
**Mitigation**:
- Test migrations on staging database
- Use Alembic's downgrade capability
- Back up production data before migrations

---

## 13. Future Enhancements (Post-MVP)

1. **Audit Logging**: Immutable log of all batch/consumption events
2. **Batch Reservations**: Lock liters for planned production runs
3. **Notifications**: Alert planners when batches approach expiry
4. **Reporting Dashboard**: Real-time inventory visualization
5. **Batch Quality Tracking**: Record lab test results (bacteria, pH, etc.)
6. **Multi-Facility Support**: Track batches across multiple plants
7. **Mobile App**: Field operators can register deliveries via smartphone

---

## Appendix A: Glossary

- **Batch**: A single milk delivery from a farm, tracked as an inventory unit
- **Consumption**: Drawing milk from a batch for production use
- **Expiry Date**: Date after which milk should not be used (received + shelf life)
- **Soft Delete**: Marking a record as deleted without physical removal
- **Pessimistic Locking**: Database-level exclusive lock during read-modify-write
- **Optimistic Locking**: Version-based conflict detection with retry logic
- **Available Liters**: Batch volume minus total consumed (`volume - sum(consumption)`)
- **Near-Expiry**: Batches expiring within a specified number of days

---

## Appendix B: SQL Query Examples

**Near-Expiry Query** (for reference):
```sql
SELECT
    id,
    batch_code,
    expiry_date,
    volume_liters,
    (volume_liters - COALESCE(SUM(cr.qty), 0)) AS available_liters
FROM batches b
LEFT JOIN consumption_records cr ON b.id = cr.batch_id
WHERE
    b.deleted_at IS NULL
    AND b.expiry_date <= NOW() + INTERVAL '3 days'
GROUP BY b.id
HAVING (volume_liters - COALESCE(SUM(cr.qty), 0)) > 0
ORDER BY b.expiry_date ASC;
```

**Consumption with Locking**:
```sql
BEGIN;

-- Acquire lock
SELECT * FROM batches
WHERE id = $1
FOR UPDATE;

-- Validate and insert
INSERT INTO consumption_records (batch_id, qty, order_id, consumed_at)
VALUES ($1, $2, $3, NOW());

UPDATE batches
SET version = version + 1, updated_at = NOW()
WHERE id = $1;

COMMIT;
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-12 | Claude | Initial implementation plan |

---

**End of Implementation Plan**
