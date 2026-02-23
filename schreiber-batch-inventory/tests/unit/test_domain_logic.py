"""Unit tests for domain logic."""

from datetime import datetime, timedelta

import pytest

from app.domain.models import Batch, ConsumptionRecord


class TestBatchCreation:
    """Tests for Batch factory method."""

    def test_expiry_date_computed_correctly(self):
        """Expiry date should be received_at + shelf_life_days."""
        received = datetime(2025, 12, 4, 8, 30)
        shelf_life = 7
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=received,
            shelf_life_days=shelf_life,
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        expected_expiry = datetime(2025, 12, 11, 8, 30)
        assert batch.expiry_date == expected_expiry

    def test_batch_defaults(self):
        """Batch should have default version=1 and deleted_at=None."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=500.0,
            fat_percent=2.5,
        )
        assert batch.version == 1
        assert batch.deleted_at is None


class TestAvailableLiters:
    """Tests for available_liters computed property."""

    def test_available_liters_no_consumption(self):
        """Available liters should equal volume when no consumption."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        # Simulate empty consumption_records list
        batch.consumption_records = []
        assert batch.available_liters == 1000.0

    def test_available_liters_with_consumption(self):
        """Available liters should equal volume minus total consumed."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        # Simulate consumption records
        record1 = ConsumptionRecord(batch_id=1, qty=250.0)
        record2 = ConsumptionRecord(batch_id=1, qty=100.0)
        batch.consumption_records = [record1, record2]
        assert batch.available_liters == 650.0

    def test_available_liters_fully_consumed(self):
        """Available liters should be 0 when fully consumed."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=100.0,
            fat_percent=3.5,
        )
        record = ConsumptionRecord(batch_id=1, qty=100.0)
        batch.consumption_records = [record]
        assert batch.available_liters == 0.0

    def test_available_liters_fractional(self):
        """Available liters should support fractional values."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=100.5,
            fat_percent=3.5,
        )
        record = ConsumptionRecord(batch_id=1, qty=50.25)
        batch.consumption_records = [record]
        assert batch.available_liters == pytest.approx(50.25)

    def test_available_liters_not_negative(self):
        """Available liters should not go below zero."""
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=datetime(2025, 12, 4),
            shelf_life_days=7,
            volume_liters=100.0,
            fat_percent=3.5,
        )
        record = ConsumptionRecord(batch_id=1, qty=150.0)
        batch.consumption_records = [record]
        assert batch.available_liters == 0.0


class TestBatchExpiry:
    """Tests for is_expired property."""

    def test_not_expired_future_date(self):
        """Batch with future expiry date should not be expired."""
        future = datetime.utcnow() + timedelta(days=7)
        batch = Batch(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            expiry_date=future,
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        assert batch.is_expired is False

    def test_expired_past_date(self):
        """Batch with past expiry date should be expired."""
        past = datetime.utcnow() - timedelta(days=1)
        batch = Batch(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow() - timedelta(days=8),
            shelf_life_days=7,
            expiry_date=past,
            volume_liters=1000.0,
            fat_percent=3.5,
        )
        assert batch.is_expired is True


class TestBatchSoftDelete:
    """Tests for is_deleted property."""

    def test_not_deleted_when_deleted_at_is_none(self):
        """Batch with no deleted_at should not be deleted."""
        batch = Batch(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            volume_liters=1000.0,
            fat_percent=3.5,
            deleted_at=None,
        )
        assert batch.is_deleted is False

    def test_deleted_when_deleted_at_is_set(self):
        """Batch with deleted_at timestamp should be deleted."""
        batch = Batch(
            batch_code="SCH-20251204-0001",
            received_at=datetime.utcnow(),
            shelf_life_days=7,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            volume_liters=1000.0,
            fat_percent=3.5,
            deleted_at=datetime.utcnow(),
        )
        assert batch.is_deleted is True


class TestExpiryDateCalculation:
    """Tests for expiry date calculation via factory method."""

    def test_shelf_life_1_day(self):
        """1-day shelf life should expire tomorrow."""
        received = datetime(2025, 12, 4, 0, 0, 0)
        batch = Batch.create(
            batch_code="SCH-20251204-0001",
            received_at=received,
            shelf_life_days=1,
            volume_liters=100.0,
            fat_percent=3.5,
        )
        assert batch.expiry_date == datetime(2025, 12, 5, 0, 0, 0)

    def test_shelf_life_30_days(self):
        """30-day shelf life should compute correctly."""
        received = datetime(2025, 12, 1, 12, 0, 0)
        batch = Batch.create(
            batch_code="SCH-20251201-0001",
            received_at=received,
            shelf_life_days=30,
            volume_liters=500.0,
            fat_percent=2.0,
        )
        assert batch.expiry_date == datetime(2025, 12, 31, 12, 0, 0)
