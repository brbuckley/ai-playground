# Testing Strategy — Schreiber Foods Batch Inventory

## Overview

This document outlines the comprehensive testing strategy for the batch inventory system, covering unit tests, integration tests, and concurrency tests. The goal is to achieve 90%+ code coverage while ensuring correctness under concurrent operations.

---

## Test Pyramid

```
       /\
      /  \     E2E Tests (Manual/Optional)
     /____\
    /      \   Integration Tests (~30 tests)
   /________\
  /          \ Unit Tests (~50 tests)
 /____________\
```

**Distribution**:
- **70% Unit Tests**: Fast, isolated tests of business logic
- **25% Integration Tests**: API endpoint tests with test database
- **5% Concurrency Tests**: Specialized tests for race conditions

---

## 1. Unit Tests

### 1.1 Domain Model Tests (tests/unit/test_models.py)

**Target**: Batch and ConsumptionRecord models

#### Test Cases

```python
def test_batch_expiry_date_computed_correctly():
    """Verify expiry_date = received_at + shelf_life_days."""
    received = datetime(2025, 12, 4, 8, 30)
    batch = Batch.create(
        batch_code="SCH-20251204-0001",
        received_at=received,
        shelf_life_days=7,
        volume_liters=1000.0,
        fat_percent=3.5,
    )

    expected_expiry = datetime(2025, 12, 11, 8, 30)
    assert batch.expiry_date == expected_expiry


def test_available_liters_with_no_consumption():
    """Available liters equals total volume when no consumption."""
    batch = Batch(volume_liters=1000.0, consumption_records=[])
    assert batch.available_liters == 1000.0


def test_available_liters_with_consumption():
    """Available liters calculated correctly with consumption records."""
    batch = Batch(volume_liters=1000.0)
    batch.consumption_records = [
        ConsumptionRecord(qty=250.0),
        ConsumptionRecord(qty=100.0),
        ConsumptionRecord(qty=50.5),
    ]

    assert batch.available_liters == 599.5  # 1000 - 400.5


def test_fractional_liters_precision():
    """Support fractional liters with decimal precision."""
    batch = Batch(volume_liters=100.25)
    batch.consumption_records = [ConsumptionRecord(qty=50.125)]

    assert batch.available_liters == 50.125


def test_is_expired_property():
    """Test batch expiry status."""
    # Expired batch
    past_date = datetime.utcnow() - timedelta(days=1)
    expired_batch = Batch(expiry_date=past_date)
    assert expired_batch.is_expired is True

    # Fresh batch
    future_date = datetime.utcnow() + timedelta(days=7)
    fresh_batch = Batch(expiry_date=future_date)
    assert fresh_batch.is_expired is False


def test_is_deleted_property():
    """Test soft delete status."""
    # Active batch
    active = Batch(deleted_at=None)
    assert active.is_deleted is False

    # Deleted batch
    deleted = Batch(deleted_at=datetime.utcnow())
    assert deleted.is_deleted is True


def test_batch_code_pattern_validation():
    """Ensure batch_code matches SCH-YYYYMMDD-XXXX pattern."""
    valid_codes = [
        "SCH-20251204-0001",
        "SCH-19990101-9999",
        "SCH-20260212-0042",
    ]

    invalid_codes = [
        "INVALID",
        "SCH-2025-0001",  # Wrong date format
        "SCH-20251204-001",  # Wrong suffix length
        "ABC-20251204-0001",  # Wrong prefix
    ]

    # Test with Pydantic schema validation
    for code in valid_codes:
        request = BatchCreateRequest(
            batch_code=code,
            received_at=datetime.utcnow(),
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        assert request.batch_code == code

    for code in invalid_codes:
        with pytest.raises(ValidationError):
            BatchCreateRequest(
                batch_code=code,
                received_at=datetime.utcnow(),
                volume_liters=1000.0,
                fat_percent=3.5,
            )
```

### 1.2 Business Logic Tests (tests/unit/test_batch_service.py)

**Target**: BatchService methods

#### Test Cases

```python
def test_create_batch_computes_expiry():
    """Service correctly computes expiry date on creation."""
    service = BatchService(session)

    received = datetime(2025, 12, 4, 8, 30)
    batch = service.create_batch(
        batch_code="SCH-20251204-0001",
        received_at=received,
        shelf_life_days=10,
        volume_liters=1000.0,
        fat_percent=3.5,
    )

    expected_expiry = received + timedelta(days=10)
    assert batch.expiry_date == expected_expiry


def test_create_batch_duplicate_code_raises_error():
    """Creating batch with duplicate code raises exception."""
    service = BatchService(session)

    # Create first batch
    service.create_batch(
        batch_code="SCH-20251204-0001",
        received_at=datetime.utcnow(),
        shelf_life_days=7,
        volume_liters=1000.0,
        fat_percent=3.5,
    )

    # Attempt duplicate
    with pytest.raises(DuplicateBatchCodeError):
        service.create_batch(
            batch_code="SCH-20251204-0001",  # Duplicate
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            volume_liters=500.0,
            fat_percent=3.5,
        )
```

### 1.3 Validation Tests (tests/unit/test_validation.py)

**Target**: Pydantic schema validation

#### Test Cases

```python
def test_batch_create_request_validation():
    """Test input validation rules."""

    # Valid request
    valid = BatchCreateRequest(
        batch_code="SCH-20251204-0001",
        received_at=datetime.utcnow(),
        shelf_life_days=7,
        volume_liters=1000.0,
        fat_percent=3.5,
    )
    assert valid.volume_liters == 1000.0

    # Invalid: shelf_life_days out of range
    with pytest.raises(ValidationError):
        BatchCreateRequest(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=31,  # Max is 30
            volume_liters=1000.0,
            fat_percent=3.5,
        )

    # Invalid: negative volume
    with pytest.raises(ValidationError):
        BatchCreateRequest(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            volume_liters=-100.0,  # Must be >= 0
            fat_percent=3.5,
        )

    # Invalid: fat_percent > 100
    with pytest.raises(ValidationError):
        BatchCreateRequest(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            volume_liters=1000.0,
            fat_percent=150.0,  # Max is 100
        )


def test_consume_request_validation():
    """Test consumption request validation."""

    # Valid
    valid = ConsumeRequest(qty=250.0, order_id="ORDER-001")
    assert valid.qty == 250.0

    # Invalid: zero quantity
    with pytest.raises(ValidationError):
        ConsumeRequest(qty=0.0)

    # Invalid: negative quantity
    with pytest.raises(ValidationError):
        ConsumeRequest(qty=-50.0)
```

---

## 2. Integration Tests

### 2.1 API Endpoint Tests (tests/integration/test_batch_api.py)

**Target**: Full request/response flow with test database

#### Setup

```python
@pytest.fixture(autouse=True)
def reset_database(session):
    """Clear database before each test."""
    session.exec(delete(ConsumptionRecord))
    session.exec(delete(Batch))
    session.commit()
```

#### Test Cases

##### POST /api/batches

```python
def test_create_batch_success(client):
    """Successfully create a new batch."""
    response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["batch_code"] == "SCH-20251204-0001"
    assert data["available_liters"] == 1000.0
    assert data["version"] == 1
    assert data["is_expired"] is False


def test_create_batch_duplicate_code(client):
    """Creating duplicate batch_code returns 409."""
    batch_data = {
        "batch_code": "SCH-20251204-0001",
        "received_at": "2025-12-04T08:30:00Z",
        "shelf_life_days": 7,
        "volume_liters": 1000.0,
        "fat_percent": 3.5,
    }

    # First creation succeeds
    client.post("/api/batches/", json=batch_data)

    # Second creation fails
    response = client.post("/api/batches/", json=batch_data)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_batch_invalid_batch_code(client):
    """Invalid batch_code format returns 422."""
    response = client.post(
        "/api/batches/",
        json={
            "batch_code": "INVALID-CODE",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )

    assert response.status_code == 422
```

##### GET /api/batches

```python
def test_list_batches(client):
    """List returns all active batches."""
    # Create 3 batches
    for i in range(1, 4):
        client.post(
            "/api/batches/",
            json={
                "batch_code": f"SCH-20251204-000{i}",
                "received_at": "2025-12-04T08:30:00Z",
                "shelf_life_days": 7,
                "volume_liters": 1000.0,
                "fat_percent": 3.5,
            },
        )

    # List all
    response = client.get("/api/batches/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["batches"]) == 3


def test_list_batches_excludes_deleted(client):
    """Deleted batches are not included in list."""
    # Create batch
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    # Delete it
    client.delete(f"/api/batches/{batch_id}")

    # List should be empty
    response = client.get("/api/batches/")
    assert response.json()["total"] == 0


def test_list_batches_pagination(client):
    """Pagination parameters work correctly."""
    # Create 10 batches
    for i in range(1, 11):
        client.post(
            "/api/batches/",
            json={
                "batch_code": f"SCH-20251204-{i:04d}",
                "received_at": "2025-12-04T08:30:00Z",
                "shelf_life_days": 7,
                "volume_liters": 1000.0,
                "fat_percent": 3.5,
            },
        )

    # Get first page (5 items)
    response = client.get("/api/batches/?skip=0&limit=5")
    assert len(response.json()["batches"]) == 5

    # Get second page
    response = client.get("/api/batches/?skip=5&limit=5")
    assert len(response.json()["batches"]) == 5
```

##### GET /api/batches/{id}

```python
def test_get_batch_success(client):
    """Retrieve batch by ID."""
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    response = client.get(f"/api/batches/{batch_id}")
    assert response.status_code == 200
    assert response.json()["id"] == batch_id


def test_get_batch_not_found(client):
    """Non-existent batch returns 404."""
    response = client.get("/api/batches/99999")
    assert response.status_code == 404


def test_get_deleted_batch_not_found(client):
    """Deleted batch returns 404."""
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    # Delete it
    client.delete(f"/api/batches/{batch_id}")

    # Try to retrieve
    response = client.get(f"/api/batches/{batch_id}")
    assert response.status_code == 404
```

##### POST /api/batches/{id}/consume

```python
def test_consume_batch_success(client):
    """Successfully consume from batch."""
    # Create batch
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    # Consume 250L
    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 250.0, "order_id": "ORDER-001"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["qty_consumed"] == 250.0
    assert data["available_liters"] == 750.0
    assert data["order_id"] == "ORDER-001"


def test_consume_fractional_liters(client):
    """Support fractional liter consumption."""
    batch_id = create_test_batch(client, volume=100.5)

    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 50.25},
    )

    assert response.status_code == 200
    assert response.json()["available_liters"] == 50.25


def test_consume_more_than_available(client):
    """Consuming more than available returns 409."""
    batch_id = create_test_batch(client, volume=100.0)

    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 150.0},
    )

    assert response.status_code == 409
    assert "insufficient" in response.json()["detail"].lower()


def test_consume_deleted_batch(client):
    """Cannot consume from deleted batch."""
    batch_id = create_test_batch(client)
    client.delete(f"/api/batches/{batch_id}")

    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 10.0},
    )

    assert response.status_code == 409
    assert "deleted" in response.json()["detail"].lower()


def test_consume_expired_batch(client):
    """Cannot consume from expired batch."""
    # Create batch that expired yesterday
    past_date = (datetime.utcnow() - timedelta(days=8)).isoformat() + "Z"

    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": past_date,
            "shelf_life_days": 7,  # Expired 1 day ago
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 10.0},
    )

    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()


def test_multiple_consumptions_update_available(client):
    """Multiple consumptions correctly update available liters."""
    batch_id = create_test_batch(client, volume=1000.0)

    # First consumption: 200L
    client.post(f"/api/batches/{batch_id}/consume", json={"qty": 200.0})

    # Second consumption: 300L
    response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 300.0},
    )

    assert response.json()["available_liters"] == 500.0  # 1000 - 200 - 300
```

##### GET /api/batches/near-expiry

```python
def test_near_expiry_returns_matching_batches(client):
    """Near-expiry query returns correct batches."""
    now = datetime.utcnow()

    # Batch expiring in 2 days (should be included)
    expires_soon = (now + timedelta(days=2 - 7)).isoformat() + "Z"
    client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": expires_soon,
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )

    # Batch expiring in 10 days (should NOT be included)
    expires_later = (now + timedelta(days=10 - 7)).isoformat() + "Z"
    client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0002",
            "received_at": expires_later,
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )

    # Query for batches expiring within 3 days
    response = client.get("/api/batches/near-expiry?n_days=3")

    assert response.status_code == 200
    batches = response.json()["batches"]
    assert len(batches) == 1
    assert batches[0]["batch_code"] == "SCH-20251204-0001"


def test_near_expiry_excludes_zero_available(client):
    """Near-expiry excludes batches with no available volume."""
    # Create batch expiring soon
    batch_id = create_test_batch(
        client,
        batch_code="SCH-20251204-0001",
        received_at=(datetime.utcnow() + timedelta(days=-5)).isoformat() + "Z",
        shelf_life_days=7,  # Expires in 2 days
        volume=100.0,
    )

    # Consume all volume
    client.post(f"/api/batches/{batch_id}/consume", json={"qty": 100.0})

    # Query near-expiry
    response = client.get("/api/batches/near-expiry?n_days=3")

    # Should be excluded (zero available)
    assert response.json()["total"] == 0


def test_near_expiry_sorted_by_expiry_date(client):
    """Near-expiry results sorted soonest first."""
    # Create 3 batches with different expiry dates
    for days_offset in [3, 1, 2]:
        received = (datetime.utcnow() + timedelta(days=days_offset - 7)).isoformat() + "Z"
        client.post(
            "/api/batches/",
            json={
                "batch_code": f"SCH-20251204-000{days_offset}",
                "received_at": received,
                "shelf_life_days": 7,
                "volume_liters": 1000.0,
                "fat_percent": 3.5,
            },
        )

    response = client.get("/api/batches/near-expiry?n_days=5")
    batches = response.json()["batches"]

    # Should be sorted: 1 day, 2 days, 3 days
    assert batches[0]["batch_code"] == "SCH-20251204-0001"
    assert batches[1]["batch_code"] == "SCH-20251204-0002"
    assert batches[2]["batch_code"] == "SCH-20251204-0003"
```

##### DELETE /api/batches/{id}

```python
def test_delete_batch_success(client):
    """Successfully soft-delete a batch."""
    batch_id = create_test_batch(client)

    response = client.delete(f"/api/batches/{batch_id}")
    assert response.status_code == 204

    # Verify batch is soft-deleted (not in list)
    list_response = client.get("/api/batches/")
    assert list_response.json()["total"] == 0


def test_delete_batch_not_found(client):
    """Deleting non-existent batch returns 404."""
    response = client.delete("/api/batches/99999")
    assert response.status_code == 404


def test_delete_already_deleted_batch(client):
    """Deleting already-deleted batch returns 409."""
    batch_id = create_test_batch(client)

    # First delete succeeds
    client.delete(f"/api/batches/{batch_id}")

    # Second delete fails
    response = client.delete(f"/api/batches/{batch_id}")
    assert response.status_code == 409
```

---

## 3. Concurrency Tests

### 3.1 Thread-Based Concurrency (tests/concurrency/test_concurrent_consumption.py)

**Target**: Verify atomic consumption under concurrent threads

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def test_concurrent_consumption_prevents_overuse(client, session):
    """
    10 threads attempt to consume 15L each from 100L batch.
    Expected: Only 6 succeed (90L total), 4 fail with 409.
    """
    # Create batch with 100L
    batch_id = create_test_batch(client, volume=100.0)

    results = []

    def consume_15L():
        """Attempt to consume 15L."""
        try:
            response = client.post(
                f"/api/batches/{batch_id}/consume",
                json={"qty": 15.0},
            )
            return response.status_code
        except Exception as e:
            return None

    # Launch 10 concurrent requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(consume_15L) for _ in range(10)]
        for future in as_completed(futures):
            results.append(future.result())

    # Verify results
    successes = [r for r in results if r == 200]
    conflicts = [r for r in results if r == 409]

    assert len(successes) == 6, f"Expected 6 successes, got {len(successes)}"
    assert len(conflicts) == 4, f"Expected 4 conflicts, got {len(conflicts)}"

    # Verify final batch state
    batch_response = client.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == 10.0  # 100 - 90


def test_no_lost_consumption_records(client, session):
    """
    Verify all successful consumptions are recorded in database.
    100 threads consume 5L each from 1000L batch.
    """
    batch_id = create_test_batch(client, volume=1000.0)

    success_count = 0
    lock = threading.Lock()

    def consume_5L():
        nonlocal success_count
        response = client.post(
            f"/api/batches/{batch_id}/consume",
            json={"qty": 5.0},
        )
        if response.status_code == 200:
            with lock:
                success_count += 1

    # Launch 100 concurrent requests
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(consume_5L) for _ in range(100)]
        for future in as_completed(futures):
            future.result()

    # Verify database records match successful requests
    from app.domain.models import ConsumptionRecord
    records = session.exec(
        select(ConsumptionRecord).where(ConsumptionRecord.batch_id == batch_id)
    ).all()

    assert len(records) == success_count
    assert sum(r.qty for r in records) == success_count * 5.0
```

### 3.2 Process-Based Concurrency (tests/concurrency/test_multiprocess.py)

**Target**: True parallelism (not GIL-limited)

```python
import multiprocessing
from functools import partial


def consume_worker(batch_id: int, qty: float, base_url: str) -> int:
    """Worker function for multiprocessing."""
    import httpx

    response = httpx.post(
        f"{base_url}/api/batches/{batch_id}/consume",
        json={"qty": qty},
    )
    return response.status_code


def test_multiprocess_concurrent_consumption(client):
    """
    Use multiprocessing to simulate true parallelism.
    10 processes consume 20L each from 150L batch.
    """
    batch_id = create_test_batch(client, volume=150.0)
    base_url = client.base_url

    # Create worker function with bound parameters
    worker = partial(consume_worker, batch_id, 20.0, base_url)

    # Launch 10 processes
    with multiprocessing.Pool(processes=10) as pool:
        results = pool.map(worker, range(10))

    successes = [r for r in results if r == 200]
    conflicts = [r for r in results if r == 409]

    # Expected: 7 succeed (140L), 3 fail
    assert len(successes) == 7
    assert len(conflicts) == 3

    # Verify final state
    batch_response = client.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == 10.0
```

### 3.3 Race Condition Stress Test (tests/concurrency/test_stress.py)

```python
def test_high_contention_stress(client):
    """
    Stress test: 200 rapid requests to same batch.
    Verify correctness under extreme contention.
    """
    batch_id = create_test_batch(client, volume=1000.0)

    results = []

    def consume_10L():
        response = client.post(
            f"/api/batches/{batch_id}/consume",
            json={"qty": 10.0},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(consume_10L) for _ in range(200)]
        for future in as_completed(futures):
            results.append(future.result())

    successes = [r for r in results if r == 200]

    # At most 100 should succeed (1000L / 10L)
    assert len(successes) <= 100

    # Verify available liters is correct
    batch_response = client.get(f"/api/batches/{batch_id}")
    available = batch_response.json()["available_liters"]

    expected = 1000.0 - (len(successes) * 10.0)
    assert available == expected
```

---

## 4. Test Coverage

### 4.1 Coverage Goals

| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| Domain Models | 95%+ | Critical |
| Repository Layer | 90%+ | Critical |
| Service Layer | 90%+ | Critical |
| API Endpoints | 85%+ | High |
| Exception Handling | 90%+ | High |

### 4.2 Running Coverage Reports

```bash
# Run tests with coverage
pytest --cov=app --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html

# Coverage summary
pytest --cov=app --cov-report=term-missing
```

### 4.3 Coverage Exclusions

Exclude from coverage:
- `__init__.py` files (imports only)
- Migration scripts
- Configuration files
- Test fixtures

---

## 5. Test Execution

### 5.1 Running Tests

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
pytest tests/concurrency/

# Run with verbose output
pytest -v

# Run specific test
pytest tests/unit/test_models.py::test_expiry_date_computed_correctly

# Run tests matching pattern
pytest -k "consume"
```

### 5.2 Continuous Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost/test_db
        run: |
          pytest --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---

## 6. Helper Utilities

### 6.1 Test Data Factories

```python
# tests/factories.py

def create_test_batch(
    client,
    batch_code: str = "SCH-20251204-0001",
    received_at: str | None = None,
    shelf_life_days: int = 7,
    volume: float = 1000.0,
    fat_percent: float = 3.5,
) -> int:
    """Helper to create a test batch and return its ID."""
    if received_at is None:
        received_at = datetime.utcnow().isoformat() + "Z"

    response = client.post(
        "/api/batches/",
        json={
            "batch_code": batch_code,
            "received_at": received_at,
            "shelf_life_days": shelf_life_days,
            "volume_liters": volume,
            "fat_percent": fat_percent,
        },
    )
    return response.json()["id"]
```

---

## Summary

This testing strategy ensures:
- **Correctness**: Business logic is validated through unit tests
- **Reliability**: API contracts are verified through integration tests
- **Concurrency Safety**: Race conditions are prevented and tested
- **Coverage**: 90%+ code coverage across critical components

All tests should be automated and run in CI/CD pipeline before deployment.
