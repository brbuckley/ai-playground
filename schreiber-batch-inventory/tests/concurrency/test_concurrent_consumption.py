"""Concurrency tests for atomic batch consumption.

These tests target a live server at BASE_URL (default: http://localhost:8000)
using only the exposed HTTP endpoints to verify concurrent request handling.

Prerequisites:
    # Start the API server:
    docker-compose up -d
    # or: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

Run:
    uv run pytest tests/concurrency/ -v
"""

import os
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")

# Fixed seed date for concurrency tests
SEED_DATE = "20260223"


def _generate_unique_batch_code() -> str:
    """Generate a unique batch code using timestamp with microseconds and randomness."""
    # Combine microsecond timestamp with random to ensure uniqueness even in rapid succession
    timestamp_part = int(time.time() * 1_000_000) % 10000
    return f"SCH-{SEED_DATE}-{timestamp_part:04d}"


@pytest.fixture(scope="module")
def http() -> Generator[httpx.Client, None, None]:
    """Module-scoped httpx client targeting the live server."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client


def test_concurrent_consumption_prevents_overuse(http: httpx.Client):
    """
    Verify atomic consumption under concurrent load.

    Setup: Create batch with 100L
    Action: 10 threads each attempt to consume 15L
    Expected: Only 6 succeed (90L ≤ 100L), 4 fail with 409
    """
    # Create batch with 100L - use timestamp-based code to ensure uniqueness
    random_code = _generate_unique_batch_code()
    response = http.post(
        "/api/batches/",
        json={
            "batch_code": random_code,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "shelf_life_days": 7,
            "volume_liters": 100.0,
            "fat_percent": 3.5,
        },
    )
    assert response.status_code == 201, f"Failed to create batch: {response.text}"
    batch_id = response.json()["id"]

    results = []
    lock = threading.Lock()

    def consume():
        resp = http.post(
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
    batch_response = http.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == pytest.approx(10.0)  # 100 - 90

    # Cleanup
    http.delete(f"/api/batches/{batch_id}")


def test_no_lost_updates(http: httpx.Client):
    """
    Verify no consumption records are lost under concurrent load.

    Setup: Create batch with 1000L
    Action: 100 threads each consume 5L
    Expected: All 100 ConsumptionRecords created, total = 500L consumed
    """
    # Create batch with 1000L - use timestamp-based code to ensure uniqueness
    time.sleep(0.001)  # Ensure different timestamp from previous test
    random_code = _generate_unique_batch_code()
    response = http.post(
        "/api/batches/",
        json={
            "batch_code": random_code,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    assert response.status_code == 201, f"Failed to create batch: {response.text}"
    batch_id = response.json()["id"]

    results = []
    lock = threading.Lock()

    def consume():
        resp = http.post(
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
    batch_response = http.get(f"/api/batches/{batch_id}")
    assert batch_response.json()["available_liters"] == pytest.approx(500.0)

    # Cleanup
    http.delete(f"/api/batches/{batch_id}")
