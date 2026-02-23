"""Manual concurrency stress test script.

Usage:
    python scripts/simulate_concurrent_ops.py

Prerequisites:
    - API server running on localhost:8000
    - Database populated or empty (will create a test batch)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx

BASE_URL = "http://localhost:8000/api"


def create_test_batch(volume: float = 100.0) -> dict:
    """Create a test batch for simulation."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    batch_code = f"SCH-{timestamp}-{int(time.time()) % 9999:04d}"

    response = httpx.post(
        f"{BASE_URL}/batches/",
        json={
            "batch_code": batch_code,
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "shelf_life_days": 7,
            "volume_liters": volume,
            "fat_percent": 3.5,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def consume_from_batch(batch_id: int, qty: float, worker_id: int) -> dict:
    """Attempt to consume from a batch."""
    try:
        response = httpx.post(
            f"{BASE_URL}/batches/{batch_id}/consume",
            json={"qty": qty, "order_id": f"SIM-{worker_id:04d}"},
            timeout=10,
        )
        return {
            "worker_id": worker_id,
            "status_code": response.status_code,
            "success": response.status_code == 200,
        }
    except Exception as e:
        return {"worker_id": worker_id, "status_code": -1, "error": str(e), "success": False}


def run_simulation(
    volume: float = 100.0,
    qty_per_request: float = 15.0,
    num_workers: int = 10,
) -> None:
    """Run concurrent consumption simulation."""
    print(f"\n{'=' * 60}")
    print("Concurrent Consumption Simulation")
    print(f"{'=' * 60}")
    print(f"Batch volume: {volume}L")
    print(f"Qty per request: {qty_per_request}L")
    print(f"Number of workers: {num_workers}")
    print(f"Expected max successes: {int(volume // qty_per_request)}")
    print(f"{'=' * 60}\n")

    # Create test batch
    print("Creating test batch...")
    batch = create_test_batch(volume=volume)
    batch_id = batch["id"]
    print(f"Created batch ID: {batch_id} (code: {batch['batch_code']})")

    # Run concurrent consumptions
    print(f"\nLaunching {num_workers} concurrent consumption requests...")
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(consume_from_batch, batch_id, qty_per_request, i): i
            for i in range(num_workers)
        }
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.time() - start_time

    # Analyze results
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    conflicts = [r for r in results if r.get("status_code") == 409]

    print(f"\n{'=' * 60}")
    print(f"Results (completed in {elapsed:.2f}s):")
    print(f"  Successful consumptions: {len(successes)}")
    print(f"  Conflicts (409): {len(conflicts)}")
    print(f"  Other failures: {len(failures) - len(conflicts)}")

    total_consumed = len(successes) * qty_per_request
    print(f"\n  Total consumed: {total_consumed}L")
    print(f"  Batch volume: {volume}L")
    print(f"  Integrity check: {'PASS' if total_consumed <= volume else 'FAIL'}")

    # Verify final state via API
    response = httpx.get(f"{BASE_URL}/batches/{batch_id}")
    final_batch = response.json()
    print(f"  Available liters (API): {final_batch['available_liters']}L")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    try:
        # Test API connectivity
        httpx.get(f"{BASE_URL.replace('/api', '')}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"ERROR: Cannot connect to API at {BASE_URL.replace('/api', '')}")
        print("Make sure the API server is running: uvicorn app.main:app --reload")
        sys.exit(1)

    run_simulation(volume=100.0, qty_per_request=15.0, num_workers=10)
    run_simulation(volume=1000.0, qty_per_request=5.0, num_workers=50)
