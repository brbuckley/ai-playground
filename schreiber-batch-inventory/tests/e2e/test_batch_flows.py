"""E2E tests for the schreiber-batch-inventory API.

These tests target a live server at BASE_URL (default: http://localhost:8000)
using only the exposed HTTP endpoints — no direct code or database access.

Prerequisites:
    # Start the API server (pick one approach):
    docker-compose up -d
    # or: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

Run:
    uv run pytest tests/e2e/ -v
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")

# Fixed seed date used to generate unique batch codes across all scenarios.
SEED_DATE = "20260223"

_now = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Seed data — a mix of expired and active batches for different test scenarios.
# _expected_expired is an internal assertion hint removed before posting to the API.
# ---------------------------------------------------------------------------
BATCH_SEEDS: list[dict[str, Any]] = [
    {
        # Received 10 days ago with 7-day shelf life → expired 3 days ago
        "batch_code": f"SCH-{SEED_DATE}-1001",
        "received_at": (_now - timedelta(days=10)).isoformat(),
        "shelf_life_days": 7,
        "volume_liters": 500.0,
        "fat_percent": 3.5,
        "_expected_expired": True,
    },
    {
        # Received 1 day ago with 5-day shelf life → expires in 4 days (active)
        "batch_code": f"SCH-{SEED_DATE}-1002",
        "received_at": (_now - timedelta(days=1)).isoformat(),
        "shelf_life_days": 5,
        "volume_liters": 800.0,
        "fat_percent": 2.0,
        "_expected_expired": False,
    },
    {
        # Received now with 30-day shelf life → active; used for single-consumption test
        "batch_code": f"SCH-{SEED_DATE}-1003",
        "received_at": _now.isoformat(),
        "shelf_life_days": 30,
        "volume_liters": 1200.0,
        "fat_percent": 3.8,
        "_expected_expired": False,
    },
    {
        # Received 6 h ago with 14-day shelf life → active; used for cumulative-consumption test
        "batch_code": f"SCH-{SEED_DATE}-1004",
        "received_at": (_now - timedelta(hours=6)).isoformat(),
        "shelf_life_days": 14,
        "volume_liters": 600.0,
        "fat_percent": 4.0,
        "_expected_expired": False,
    },
    {
        # Received 3 h ago with 28-day shelf life → active; used for order-id test
        "batch_code": f"SCH-{SEED_DATE}-1005",
        "received_at": (_now - timedelta(hours=3)).isoformat(),
        "shelf_life_days": 28,
        "volume_liters": 1000.0,
        "fat_percent": 2.5,
        "_expected_expired": False,
    },
]

_INTERNAL_KEYS: frozenset[str] = frozenset({"_expected_expired"})


def _api_payload(seed: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *seed* with internal-only keys removed."""
    return {k: v for k, v in seed.items() if k not in _INTERNAL_KEYS}


def _find(batches: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    """Locate a created batch by its 4-digit numeric suffix, e.g. ``'1003'``."""
    code = f"SCH-{SEED_DATE}-{suffix}"
    return next(b for b in batches if b["batch_code"] == code)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def http() -> Generator[httpx.Client, None, None]:
    """Module-scoped httpx client targeting the live server."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def created_batches(http: httpx.Client) -> list[dict[str, Any]]:
    """Create all seed batches once for the module.

    Returns the API responses enriched with ``_expected_expired`` metadata
    so assertion helpers can compare actual vs. expected expiry state.
    """
    results: list[dict[str, Any]] = []
    for seed in BATCH_SEEDS:
        resp = http.post("/api/batches/", json=_api_payload(seed))
        assert resp.status_code == 201, (
            f"Seed creation failed for {seed['batch_code']}: {resp.text}"
        )
        batch: dict[str, Any] = resp.json()
        batch["_expected_expired"] = seed["_expected_expired"]
        results.append(batch)
    return results


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestSeedBatchesCreated:
    """Verify all seed batches are created with the correct initial state."""

    def test_all_five_batches_exist(self, created_batches: list[dict[str, Any]]) -> None:
        assert len(created_batches) == len(BATCH_SEEDS)

    def test_batch_codes_match_seed(self, created_batches: list[dict[str, Any]]) -> None:
        expected_codes = {s["batch_code"] for s in BATCH_SEEDS}
        actual_codes = {b["batch_code"] for b in created_batches}
        assert actual_codes == expected_codes

    def test_expiry_flags_match_expected(self, created_batches: list[dict[str, Any]]) -> None:
        for batch in created_batches:
            assert batch["is_expired"] == batch["_expected_expired"], (
                f"{batch['batch_code']}: expected is_expired={batch['_expected_expired']}, "
                f"got {batch['is_expired']}"
            )

    def test_available_liters_equal_volume_at_creation(
        self, created_batches: list[dict[str, Any]]
    ) -> None:
        for batch in created_batches:
            seed = next(s for s in BATCH_SEEDS if s["batch_code"] == batch["batch_code"])
            assert batch["available_liters"] == pytest.approx(seed["volume_liters"])


class TestPaginatedListing:
    """List batches with pagination and verify the expired flag is surfaced correctly."""

    def test_all_seed_batches_appear_in_full_listing(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        resp = http.get("/api/batches/", params={"limit": 1000})
        assert resp.status_code == 200
        returned_codes = {b["batch_code"] for b in resp.json()["batches"]}
        seed_codes = {s["batch_code"] for s in BATCH_SEEDS}
        assert seed_codes.issubset(returned_codes)

    def test_total_count_includes_all_active_batches(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        resp = http.get("/api/batches/")
        assert resp.status_code == 200
        assert resp.json()["total"] >= len(BATCH_SEEDS)

    def test_pagination_first_page_limits_result_count(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        resp = http.get("/api/batches/", params={"skip": 0, "limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()["batches"]) == 2

    def test_pagination_second_page_has_distinct_records(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        page1_ids = {
            b["id"]
            for b in http.get("/api/batches/", params={"skip": 0, "limit": 2}).json()["batches"]
        }
        page2_ids = {
            b["id"]
            for b in http.get("/api/batches/", params={"skip": 2, "limit": 2}).json()["batches"]
        }
        assert page1_ids.isdisjoint(page2_ids)

    def test_expired_batch_is_present_and_flagged(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """The list endpoint includes expired batches, but each carries is_expired=True.

        Expired batches are not silently hidden — they appear in the listing so operators
        can see and manage them.  The ``is_expired`` flag is what callers must check to
        exclude them from active-inventory views.
        """
        resp = http.get("/api/batches/", params={"limit": 1000})
        assert resp.status_code == 200
        listed = {b["batch_code"]: b for b in resp.json()["batches"]}

        expired_code = f"SCH-{SEED_DATE}-1001"
        assert expired_code in listed, "Expired batch must still appear in the listing"
        assert listed[expired_code]["is_expired"] is True

    def test_active_batches_are_not_flagged_as_expired(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        resp = http.get("/api/batches/", params={"limit": 1000})
        assert resp.status_code == 200
        listed = {b["batch_code"]: b for b in resp.json()["batches"]}

        active_codes = [f"SCH-{SEED_DATE}-100{n}" for n in range(2, 6)]
        for code in active_codes:
            if code in listed:
                assert listed[code]["is_expired"] is False, f"{code} should not be marked expired"

    def test_expired_batch_cannot_be_consumed(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """The API must reject consumption from an expired batch with HTTP 409."""
        expired = _find(created_batches, "1001")
        resp = http.post(
            f"/api/batches/{expired['id']}/consume",
            json={"qty": 10.0, "order_id": "SHOULD-FAIL"},
        )
        assert resp.status_code == 409


class TestConsumption:
    """Consume from active batches and assert available_liters is updated correctly.

    Note: tests within this class have an ordering dependency.
    ``test_get_batch_reflects_consumption`` must run after
    ``test_cumulative_consumptions_reduce_available_liters``.
    pytest executes methods in definition order, so the sequence is preserved.
    """

    def test_single_consumption_reduces_available_liters(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        batch = _find(created_batches, "1003")
        consume_qty = 300.0
        expected_remaining = batch["volume_liters"] - consume_qty

        resp = http.post(
            f"/api/batches/{batch['id']}/consume",
            json={"qty": consume_qty, "order_id": "ORDER-E2E-001"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["qty_consumed"] == pytest.approx(consume_qty)
        assert result["available_liters"] == pytest.approx(expected_remaining)

    def test_cumulative_consumptions_reduce_available_liters(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """Three sequential consumptions from batch 1004 (600 L) should leave 200 L."""
        batch = _find(created_batches, "1004")
        schedule = [
            (150.0, "ORDER-E2E-A"),
            (200.0, "ORDER-E2E-B"),
            (50.0, "ORDER-E2E-C"),
        ]
        remaining = batch["volume_liters"]
        for qty, order_id in schedule:
            resp = http.post(
                f"/api/batches/{batch['id']}/consume",
                json={"qty": qty, "order_id": order_id},
            )
            assert resp.status_code == 200
            remaining -= qty
            assert resp.json()["available_liters"] == pytest.approx(remaining)

    def test_get_batch_reflects_consumption(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """GET after cumulative consumption must return the updated available_liters."""
        batch = _find(created_batches, "1004")
        resp = http.get(f"/api/batches/{batch['id']}")
        assert resp.status_code == 200
        # 600 − 150 − 200 − 50 = 200 L
        assert resp.json()["available_liters"] == pytest.approx(200.0)

    def test_over_consumption_returns_409(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """Consuming more than the available volume must return 409 Conflict."""
        batch = _find(created_batches, "1004")
        resp = http.post(
            f"/api/batches/{batch['id']}/consume",
            json={"qty": 99999.0},
        )
        assert resp.status_code == 409
        assert "insufficient" in resp.json()["detail"].lower()

    def test_consumption_records_order_id(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        """Consumption response must echo back the supplied order_id."""
        batch = _find(created_batches, "1005")
        order_id = "ORDER-E2E-PROD-999"
        resp = http.post(
            f"/api/batches/{batch['id']}/consume",
            json={"qty": 25.0, "order_id": order_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == order_id
        assert data["batch_id"] == batch["id"]
        assert data["qty_consumed"] == pytest.approx(25.0)


class TestCleanup:
    """Delete all seed batches.  Runs last to also exercise DELETE behaviour."""

    def test_delete_all_seed_batches_returns_204(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        for batch in created_batches:
            resp = http.delete(f"/api/batches/{batch['id']}")
            assert resp.status_code == 204, (
                f"Failed to delete batch {batch['id']} ({batch['batch_code']}): {resp.text}"
            )

    def test_deleted_batches_absent_from_listing(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        resp = http.get("/api/batches/", params={"limit": 1000})
        assert resp.status_code == 200
        returned_ids = {b["id"] for b in resp.json()["batches"]}
        seed_ids = {b["id"] for b in created_batches}
        assert seed_ids.isdisjoint(returned_ids), (
            "All seed batches should be absent from the listing after deletion"
        )

    def test_deleted_batch_returns_404_on_get(
        self, http: httpx.Client, created_batches: list[dict[str, Any]]
    ) -> None:
        for batch in created_batches:
            resp = http.get(f"/api/batches/{batch['id']}")
            assert resp.status_code == 404
