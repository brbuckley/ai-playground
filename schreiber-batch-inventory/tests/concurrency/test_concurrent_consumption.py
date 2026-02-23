"""Concurrency tests for atomic batch consumption.

NOTE: These tests require a running PostgreSQL database and are intended to
be run against a real database (not SQLite in-memory). They are skipped
by default in CI unless POSTGRES_TEST_URL is set.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pytest

# Skip concurrency tests unless PostgreSQL test URL is configured
POSTGRES_TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="Concurrency tests require TEST_DATABASE_URL (PostgreSQL)",
)


@pytest.fixture(name="pg_session")
def pg_session_fixture():
    """Create a PostgreSQL session for concurrency testing."""
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine(POSTGRES_TEST_URL)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="pg_client")
def pg_client_fixture(pg_session):
    """Create test client with PostgreSQL session."""
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.main import app

    def get_session_override():
        return pg_session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()


def test_concurrent_consumption_prevents_overuse(pg_client):
    """
    Verify atomic consumption under concurrent load.

    Setup: Create batch with 100L
    Action: 10 threads each attempt to consume 15L
    Expected: Only 6 succeed (90L ≤ 100L), 4 fail with 409
    """
    # Create batch with 100L
    response = pg_client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "shelf_life_days": 7,
            "volume_liters": 100.0,
            "fat_percent": 3.5,
        },
    )
    assert response.status_code == 201
    batch_id = response.json()["id"]

    results = []
    lock = threading.Lock()

    def consume():
        resp = pg_client.post(
            f"/api/batches/{batch_id}/consume",
            json={"qty": 15.0},
        )
        with lock:
            results.append(resp.status_code)

    # Launch 10 concurrent consumers
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(consume) for _ in range(10)]
        for future in as_completed(futures):
            future.result()

    successes = [r for r in results if r == 200]
    conflicts = [r for r in results if r == 409]

    # 6 * 15 = 90 ≤ 100, 7th would exceed
    assert len(successes) == 6, f"Expected 6 successes, got {len(successes)}"
    assert len(conflicts) == 4, f"Expected 4 conflicts, got {len(conflicts)}"

    # Verify final state via API
    batch_response = pg_client.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == pytest.approx(10.0)  # 100 - 90


def test_no_lost_updates(pg_client):
    """
    Verify no consumption records are lost under concurrent load.

    Setup: Create batch with 1000L
    Action: 100 threads each consume 5L
    Expected: All 100 ConsumptionRecords created, total = 500L consumed
    """
    response = pg_client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0002",
            "received_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    assert response.status_code == 201
    batch_id = response.json()["id"]

    results = []
    lock = threading.Lock()

    def consume():
        resp = pg_client.post(
            f"/api/batches/{batch_id}/consume",
            json={"qty": 5.0, "order_id": f"ORDER-{threading.current_thread().ident}"},
        )
        with lock:
            results.append(resp.status_code)

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(consume) for _ in range(100)]
        for future in as_completed(futures):
            future.result()

    # All 100 should succeed (5 * 100 = 500 ≤ 1000)
    assert all(r == 200 for r in results), f"Some requests failed: {results}"

    # Verify final available liters
    batch_response = pg_client.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == pytest.approx(500.0)
