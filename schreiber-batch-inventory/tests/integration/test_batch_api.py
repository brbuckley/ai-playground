"""Integration tests for batch API endpoints."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


VALID_BATCH_DATA = {
    "batch_code": "SCH-20251204-0001",
    "received_at": "2025-12-04T08:30:00Z",
    "shelf_life_days": 7,
    "volume_liters": 1000.0,
    "fat_percent": 3.5,
}


def create_batch(client: TestClient, data: dict | None = None) -> dict:
    """Helper to create a batch and return response JSON."""
    response = client.post("/api/batches/", json=data or VALID_BATCH_DATA)
    assert response.status_code == 201
    return response.json()


class TestCreateBatch:
    """Tests for POST /api/batches/."""

    def test_create_batch_success(self, client: TestClient):
        """Happy path: create a valid batch."""
        response = client.post("/api/batches/", json=VALID_BATCH_DATA)

        assert response.status_code == 201
        data = response.json()
        assert data["batch_code"] == "SCH-20251204-0001"
        assert data["available_liters"] == 1000.0
        assert data["version"] == 1
        assert "id" in data
        assert "expiry_date" in data

    def test_create_batch_computes_expiry_date(self, client: TestClient):
        """Expiry date should be received_at + shelf_life_days."""
        response = client.post("/api/batches/", json=VALID_BATCH_DATA)

        data = response.json()
        received = datetime.fromisoformat(data["received_at"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(data["expiry_date"].replace("Z", "+00:00"))
        assert (expiry - received).days == VALID_BATCH_DATA["shelf_life_days"]

    def test_create_batch_duplicate_code_returns_409(self, client: TestClient):
        """Duplicate batch code should return 409 Conflict."""
        client.post("/api/batches/", json=VALID_BATCH_DATA)
        response = client.post("/api/batches/", json=VALID_BATCH_DATA)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_batch_invalid_code_format(self, client: TestClient):
        """Invalid batch code format should return 422."""
        data = {**VALID_BATCH_DATA, "batch_code": "INVALID-CODE"}
        response = client.post("/api/batches/", json=data)

        assert response.status_code == 422

    def test_create_batch_invalid_shelf_life(self, client: TestClient):
        """Shelf life outside 1-30 range should return 422."""
        data = {**VALID_BATCH_DATA, "shelf_life_days": 31}
        response = client.post("/api/batches/", json=data)

        assert response.status_code == 422

    def test_create_batch_negative_volume(self, client: TestClient):
        """Non-positive volume should return 422."""
        data = {**VALID_BATCH_DATA, "volume_liters": 0}
        response = client.post("/api/batches/", json=data)

        assert response.status_code == 422

    def test_create_batch_invalid_fat_percent(self, client: TestClient):
        """Fat percent outside 0-100 should return 422."""
        data = {**VALID_BATCH_DATA, "fat_percent": 101}
        response = client.post("/api/batches/", json=data)

        assert response.status_code == 422


class TestListBatches:
    """Tests for GET /api/batches/."""

    def test_list_batches_empty(self, client: TestClient):
        """Empty database should return empty list."""
        response = client.get("/api/batches/")

        assert response.status_code == 200
        data = response.json()
        assert data["batches"] == []
        assert data["total"] == 0

    def test_list_batches_returns_active_only(self, client: TestClient):
        """Only non-deleted batches should be returned."""
        # Create two batches
        batch1 = create_batch(client, VALID_BATCH_DATA)
        create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": "SCH-20251204-0002"},
        )

        # Delete first batch
        client.delete(f"/api/batches/{batch1['id']}")

        response = client.get("/api/batches/")
        data = response.json()
        assert data["total"] == 1
        assert data["batches"][0]["batch_code"] == "SCH-20251204-0002"


class TestGetBatch:
    """Tests for GET /api/batches/{id}."""

    def test_get_batch_success(self, client: TestClient):
        """Should return full batch details."""
        created = create_batch(client)
        response = client.get(f"/api/batches/{created['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created["id"]
        assert data["batch_code"] == "SCH-20251204-0001"

    def test_get_batch_not_found(self, client: TestClient):
        """Non-existent batch should return 404."""
        response = client.get("/api/batches/9999")

        assert response.status_code == 404

    def test_get_deleted_batch_returns_404(self, client: TestClient):
        """Deleted batch should return 404."""
        created = create_batch(client)
        client.delete(f"/api/batches/{created['id']}")

        response = client.get(f"/api/batches/{created['id']}")
        assert response.status_code == 404


class TestConsumeBatch:
    """Tests for POST /api/batches/{id}/consume."""

    def test_consume_batch_success(self, client: TestClient):
        """Happy path: create and consume from a batch."""
        created = create_batch(client)

        response = client.post(
            f"/api/batches/{created['id']}/consume",
            json={"qty": 250.0, "order_id": "ORDER-001"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["qty_consumed"] == 250.0
        assert data["available_liters"] == 750.0
        assert data["order_id"] == "ORDER-001"

    def test_consume_updates_available_liters(self, client: TestClient):
        """Multiple consumptions should cumulatively reduce available liters."""
        created = create_batch(client)

        client.post(
            f"/api/batches/{created['id']}/consume",
            json={"qty": 300.0},
        )
        response = client.post(
            f"/api/batches/{created['id']}/consume",
            json={"qty": 200.0},
        )

        assert response.status_code == 200
        assert response.json()["available_liters"] == 500.0

    def test_consume_over_available_returns_409(self, client: TestClient):
        """Consuming more than available should return 409."""
        created = create_batch(
            client,
            {**VALID_BATCH_DATA, "volume_liters": 100.0},
        )

        response = client.post(
            f"/api/batches/{created['id']}/consume",
            json={"qty": 150.0},
        )

        assert response.status_code == 409
        assert "insufficient" in response.json()["detail"].lower()

    def test_consume_deleted_batch_returns_409(self, client: TestClient):
        """Consuming from deleted batch should return 409."""
        created = create_batch(client)
        client.delete(f"/api/batches/{created['id']}")

        response = client.post(
            f"/api/batches/{created['id']}/consume",
            json={"qty": 10.0},
        )
        assert response.status_code == 409

    def test_consume_nonexistent_batch_returns_404(self, client: TestClient):
        """Consuming from non-existent batch should return 404."""
        response = client.post(
            "/api/batches/9999/consume",
            json={"qty": 10.0},
        )
        assert response.status_code == 404


class TestDeleteBatch:
    """Tests for DELETE /api/batches/{id}."""

    def test_delete_batch_success(self, client: TestClient):
        """Deleting an existing batch should return 204."""
        created = create_batch(client)
        response = client.delete(f"/api/batches/{created['id']}")

        assert response.status_code == 204

    def test_delete_nonexistent_batch_returns_404(self, client: TestClient):
        """Deleting non-existent batch should return 404."""
        response = client.delete("/api/batches/9999")

        assert response.status_code == 404

    def test_delete_already_deleted_batch_returns_409(self, client: TestClient):
        """Deleting already-deleted batch should return 409."""
        created = create_batch(client)
        client.delete(f"/api/batches/{created['id']}")

        response = client.delete(f"/api/batches/{created['id']}")
        assert response.status_code == 409


class TestNearExpiry:
    """Tests for GET /api/batches/near-expiry."""

    def test_near_expiry_returns_batches_within_window(self, client: TestClient):
        """Only batches expiring within n_days should be returned."""
        # Batch expiring in 2 days (received 5 days ago, 7-day shelf life)
        received_soon = (datetime.utcnow() - timedelta(days=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        create_batch(
            client,
            {
                "batch_code": "SCH-20251204-0001",
                "received_at": received_soon,
                "shelf_life_days": 7,
                "volume_liters": 100.0,
                "fat_percent": 3.5,
            },
        )

        # Batch expiring in 10 days (received today, 10-day shelf life)
        received_later = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        create_batch(
            client,
            {
                "batch_code": "SCH-20251204-0002",
                "received_at": received_later,
                "shelf_life_days": 10,
                "volume_liters": 200.0,
                "fat_percent": 2.0,
            },
        )

        response = client.get("/api/batches/near-expiry?n_days=3")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["batches"][0]["batch_code"] == "SCH-20251204-0001"
