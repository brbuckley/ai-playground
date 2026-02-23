"""Business logic layer for batch operations."""

from datetime import datetime
from typing import List

from sqlmodel import Session

from app.domain.models import Batch, ConsumptionRecord
from app.repositories.batch_repository import BatchRepository


class BatchService:
    """Service layer for batch business logic."""

    def __init__(self, session: Session):
        self.repository = BatchRepository(session)

    def create_batch(
        self,
        batch_code: str,
        received_at: datetime,
        shelf_life_days: int,
        volume_liters: float,
        fat_percent: float,
    ) -> Batch:
        """
        Create a new batch with business logic validation.

        Args:
            batch_code: Unique identifier
            received_at: Receipt timestamp
            shelf_life_days: Shelf life (1-30 days)
            volume_liters: Total volume
            fat_percent: Fat percentage

        Returns:
            Created batch
        """
        batch = Batch.create(
            batch_code=batch_code,
            received_at=received_at,
            shelf_life_days=shelf_life_days,
            volume_liters=volume_liters,
            fat_percent=fat_percent,
        )
        return self.repository.create(batch)

    def get_batch(self, batch_id: int) -> Batch:
        """Retrieve batch by ID."""
        return self.repository.get_by_id(batch_id)

    def list_batches(self, skip: int = 0, limit: int = 100) -> List[Batch]:
        """List active batches with pagination."""
        return self.repository.list_active(skip=skip, limit=limit)

    def get_near_expiry_batches(self, n_days: int) -> List[Batch]:
        """Get batches nearing expiry."""
        return self.repository.get_near_expiry(n_days=n_days)

    def consume_from_batch(
        self,
        batch_id: int,
        qty: float,
        order_id: str | None = None,
    ) -> ConsumptionRecord:
        """Consume liters from batch (atomic operation)."""
        return self.repository.consume(
            batch_id=batch_id,
            qty=qty,
            order_id=order_id,
        )

    def delete_batch(self, batch_id: int) -> Batch:
        """Soft-delete a batch."""
        return self.repository.soft_delete(batch_id)
