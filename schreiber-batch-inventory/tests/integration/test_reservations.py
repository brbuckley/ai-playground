"""Integration tests for batch reservation endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


# Generate test data with current timestamp to avoid expiry issues
_test_received = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_test_date_code = datetime.now(timezone.utc).strftime("%Y%m%d")

VALID_BATCH_DATA = {
    "batch_code": f"SCH-{_test_date_code}-9001",
    "received_at": _test_received,
    "shelf_life_days": 7,
    "volume_liters": 1000.0,
    "fat_percent": 3.5,
}


def create_batch(client: TestClient, data: dict | None = None) -> dict:
    """Helper to create a batch and return response JSON."""
    response = client.post("/api/batches/", json=data or VALID_BATCH_DATA)
    assert response.status_code == 201
    return response.json()


class TestCreateReservation:
    """Tests for POST /api/batches/{id}/reserve."""

    def test_create_reservation_success(self, client: TestClient):
        """Happy path: reserve liters from an active batch."""
        batch = create_batch(client)
        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 200.0, "purpose": "Production run PL-001"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["batch_id"] == batch["id"]
        assert data["reserved_qty"] == 200.0
        assert data["purpose"] == "Production run PL-001"
        assert data["is_active"] is True
        assert data["released_at"] is None
        assert "id" in data
        assert "reserved_at" in data

    def test_create_reservation_no_purpose(self, client: TestClient):
        """Reservation without purpose should succeed."""
        batch = create_batch(client)
        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 50.0},
        )

        assert response.status_code == 201
        assert response.json()["purpose"] is None

    def test_create_reservation_reduces_free_liters(self, client: TestClient):
        """Reserved liters should reduce free_liters on the batch."""
        batch = create_batch(client)
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 300.0},
        )

        batch_response = client.get(f"/api/batches/{batch['id']}")
        data = batch_response.json()
        assert data["reserved_liters"] == 300.0
        assert data["free_liters"] == 700.0
        assert data["available_liters"] == 1000.0  # unchanged

    def test_create_multiple_reservations(self, client: TestClient):
        """Multiple reservations should stack."""
        batch = create_batch(client)
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 200.0},
        )
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 300.0},
        )

        batch_response = client.get(f"/api/batches/{batch['id']}")
        data = batch_response.json()
        assert data["reserved_liters"] == 500.0
        assert data["free_liters"] == 500.0

    def test_create_reservation_insufficient_free_volume(self, client: TestClient):
        """Reserving more than free volume should return 409."""
        batch = create_batch(
            client,
            {
                **VALID_BATCH_DATA,
                "batch_code": f"SCH-{_test_date_code}-9002",
                "volume_liters": 100.0,
            },
        )
        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 150.0},
        )

        assert response.status_code == 409
        assert "insufficient" in response.json()["detail"].lower()

    def test_create_reservation_on_deleted_batch_returns_409(self, client: TestClient):
        """Reserving from deleted batch should return 409."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9003"},
        )
        client.delete(f"/api/batches/{batch['id']}")

        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 10.0},
        )
        assert response.status_code == 409

    def test_create_reservation_on_nonexistent_batch_returns_404(self, client: TestClient):
        """Reserving from non-existent batch should return 404."""
        response = client.post("/api/batches/9999/reserve", json={"reserved_qty": 10.0})
        assert response.status_code == 404

    def test_create_reservation_on_expired_batch_returns_409(self, client: TestClient):
        """Reserving from expired batch should return 409."""
        past = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        batch = create_batch(
            client,
            {
                **VALID_BATCH_DATA,
                "batch_code": f"SCH-{_test_date_code}-9004",
                "received_at": past,
                "shelf_life_days": 3,
            },
        )
        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 10.0},
        )
        assert response.status_code == 409

    def test_create_reservation_invalid_qty_returns_422(self, client: TestClient):
        """Reservation with zero or negative qty should return 422."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9005"},
        )
        response = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 0},
        )
        assert response.status_code == 422


class TestListReservations:
    """Tests for GET /api/batches/{id}/reservations."""

    def test_list_reservations_empty(self, client: TestClient):
        """Batch with no reservations should return empty list."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9010"},
        )
        response = client.get(f"/api/batches/{batch['id']}/reservations")

        assert response.status_code == 200
        data = response.json()
        assert data["reservations"] == []
        assert data["total"] == 0

    def test_list_reservations_with_entries(self, client: TestClient):
        """Should return all reservations for the batch."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9011"},
        )
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 100.0, "purpose": "Run A"},
        )
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 200.0, "purpose": "Run B"},
        )

        response = client.get(f"/api/batches/{batch['id']}/reservations")
        data = response.json()
        assert data["total"] == 2
        assert len(data["reservations"]) == 2

    def test_list_reservations_nonexistent_batch_returns_404(self, client: TestClient):
        """Listing reservations for non-existent batch should return 404."""
        response = client.get("/api/batches/9999/reservations")
        assert response.status_code == 404


class TestReleaseReservation:
    """Tests for DELETE /api/batches/{id}/reservations/{reservation_id}."""

    def test_release_reservation_success(self, client: TestClient):
        """Happy path: release an active reservation."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9020"},
        )
        create_resp = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 100.0},
        )
        reservation_id = create_resp.json()["id"]

        response = client.delete(f"/api/batches/{batch['id']}/reservations/{reservation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert data["released_at"] is not None

    def test_release_restores_free_liters(self, client: TestClient):
        """Releasing a reservation should restore free_liters on the batch."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9021"},
        )
        create_resp = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 500.0},
        )
        reservation_id = create_resp.json()["id"]

        # Verify free_liters reduced
        batch_data = client.get(f"/api/batches/{batch['id']}").json()
        assert batch_data["free_liters"] == 500.0

        # Release reservation
        client.delete(f"/api/batches/{batch['id']}/reservations/{reservation_id}")

        # Verify free_liters restored
        batch_data = client.get(f"/api/batches/{batch['id']}").json()
        assert batch_data["free_liters"] == 1000.0
        assert batch_data["reserved_liters"] == 0.0

    def test_release_already_released_returns_409(self, client: TestClient):
        """Releasing an already-released reservation should return 409."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9022"},
        )
        create_resp = client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 100.0},
        )
        reservation_id = create_resp.json()["id"]

        # First release
        client.delete(f"/api/batches/{batch['id']}/reservations/{reservation_id}")

        # Second release should fail
        response = client.delete(f"/api/batches/{batch['id']}/reservations/{reservation_id}")
        assert response.status_code == 409
        assert "already been released" in response.json()["detail"]

    def test_release_nonexistent_reservation_returns_404(self, client: TestClient):
        """Releasing a non-existent reservation should return 404."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9023"},
        )
        response = client.delete(f"/api/batches/{batch['id']}/reservations/9999")
        assert response.status_code == 404

    def test_release_nonexistent_batch_returns_404(self, client: TestClient):
        """Releasing reservation from non-existent batch should return 404."""
        response = client.delete("/api/batches/9999/reservations/1")
        assert response.status_code == 404


class TestBatchResponseWithReservations:
    """Tests verifying BatchResponse includes reservation fields."""

    def test_batch_response_includes_reservation_fields(self, client: TestClient):
        """BatchResponse should include reserved_liters and free_liters."""
        batch = create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9030"},
        )

        batch_data = client.get(f"/api/batches/{batch['id']}").json()
        assert "reserved_liters" in batch_data
        assert "free_liters" in batch_data
        assert batch_data["reserved_liters"] == 0.0
        assert batch_data["free_liters"] == batch_data["available_liters"]

    def test_list_response_includes_reservation_fields(self, client: TestClient):
        """List endpoint should also include reserved_liters and free_liters."""
        create_batch(
            client,
            {**VALID_BATCH_DATA, "batch_code": f"SCH-{_test_date_code}-9031"},
        )
        response = client.get("/api/batches/")
        batches = response.json()["batches"]
        assert len(batches) >= 1
        for b in batches:
            assert "reserved_liters" in b
            assert "free_liters" in b

    def test_consumption_does_not_affect_reservations(self, client: TestClient):
        """Consuming from a batch should not affect its active reservations."""
        batch = create_batch(
            client,
            {
                **VALID_BATCH_DATA,
                "batch_code": f"SCH-{_test_date_code}-9032",
                "volume_liters": 1000.0,
            },
        )

        # Reserve 400L
        client.post(
            f"/api/batches/{batch['id']}/reserve",
            json={"reserved_qty": 400.0},
        )

        # Consume 200L
        client.post(
            f"/api/batches/{batch['id']}/consume",
            json={"qty": 200.0},
        )

        batch_data = client.get(f"/api/batches/{batch['id']}").json()
        assert batch_data["available_liters"] == 800.0  # 1000 - 200 consumed
        assert batch_data["reserved_liters"] == 400.0  # unchanged
        assert batch_data["free_liters"] == 400.0  # 800 available - 400 reserved
