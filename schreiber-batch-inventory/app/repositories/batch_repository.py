"""Data access layer for Batch operations."""

from datetime import datetime, timedelta, timezone
from typing import List

from sqlmodel import Session, select

from app.domain.exceptions import (
    BatchDeletedError,
    BatchExpiredError,
    BatchNotFoundError,
    DuplicateBatchCodeError,
    InsufficientVolumeError,
    ReservationAlreadyReleasedError,
    ReservationNotFoundError,
)
from app.domain.models import Batch, BatchReservation, ConsumptionRecord


class BatchRepository:
    """Repository for batch database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, batch: Batch) -> Batch:
        """
        Create a new batch.

        Args:
            batch: Batch instance to persist

        Returns:
            Created batch with generated ID

        Raises:
            DuplicateBatchCodeError: If batch_code already exists
        """
        try:
            self.session.add(batch)
            self.session.commit()
            self.session.refresh(batch)
            return batch
        except Exception as e:
            self.session.rollback()
            if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                raise DuplicateBatchCodeError(batch_code=batch.batch_code)
            raise

    def get_by_id(self, batch_id: int, include_deleted: bool = False) -> Batch:
        """
        Retrieve batch by ID.

        Args:
            batch_id: Batch ID
            include_deleted: Whether to include soft-deleted batches

        Returns:
            Batch instance

        Raises:
            BatchNotFoundError: If batch doesn't exist or is deleted
        """
        statement = select(Batch).where(Batch.id == batch_id)
        if not include_deleted:
            statement = statement.where(Batch.deleted_at.is_(None))  # type: ignore[union-attr]

        batch = self.session.exec(statement).first()
        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        return batch

    def list_active(self, skip: int = 0, limit: int = 100) -> List[Batch]:
        """
        List active (non-deleted) batches.

        Args:
            skip: Pagination offset
            limit: Page size

        Returns:
            List of active batches
        """
        statement = (
            select(Batch)
            .where(Batch.deleted_at.is_(None))  # type: ignore[union-attr]
            .order_by(Batch.created_at.desc())  # type: ignore[union-attr]
            .offset(skip)
            .limit(limit)
        )
        return list(self.session.exec(statement).all())

    def get_near_expiry(self, n_days: int) -> List[Batch]:
        """
        Get batches nearing expiry with available volume.

        Args:
            n_days: Look-ahead window in days

        Returns:
            List of batches expiring within n_days, sorted by expiry_date
        """
        threshold = datetime.now(timezone.utc) + timedelta(days=n_days)

        statement = (
            select(Batch)
            .where(
                Batch.deleted_at.is_(None),  # type: ignore[union-attr]
                Batch.expiry_date <= threshold,
            )
            .order_by(Batch.expiry_date.asc())  # type: ignore[union-attr]
        )

        batches = self.session.exec(statement).all()

        # Filter for available_liters > 0 (computed property)
        return [batch for batch in batches if batch.available_liters > 0]

    def consume(
        self,
        batch_id: int,
        qty: float,
        order_id: str | None = None,
    ) -> ConsumptionRecord:
        """
        Consume liters from a batch (pessimistic locking).

        This method uses SELECT FOR UPDATE to acquire an exclusive lock
        on the batch row, ensuring atomic consumption under concurrency.

        Args:
            batch_id: Batch to consume from
            qty: Quantity to consume in liters
            order_id: Associated production order

        Returns:
            Created ConsumptionRecord

        Raises:
            BatchNotFoundError: Batch doesn't exist
            BatchDeletedError: Batch is soft-deleted
            BatchExpiredError: Batch has expired
            InsufficientVolumeError: Not enough available volume
        """
        # Acquire pessimistic lock on batch
        statement = select(Batch).where(Batch.id == batch_id).with_for_update()
        batch = self.session.exec(statement).first()

        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        # Validate batch state
        if batch.is_deleted:
            raise BatchDeletedError(batch_id=batch_id)

        if batch.is_expired:
            raise BatchExpiredError(batch_id=batch_id, expiry_date=batch.expiry_date)

        # Check available volume
        available = batch.available_liters
        if qty > available:
            raise InsufficientVolumeError(
                batch_id=batch_id,
                available=available,
                requested=qty,
            )

        # Create consumption record
        record = ConsumptionRecord(
            batch_id=batch_id,
            qty=qty,
            order_id=order_id,
        )
        self.session.add(record)

        # Update batch metadata
        batch.version += 1
        batch.updated_at = datetime.now(timezone.utc)

        # Commit transaction (releases lock)
        self.session.commit()
        self.session.refresh(record)

        return record

    def soft_delete(self, batch_id: int) -> Batch:
        """
        Soft-delete a batch.

        Args:
            batch_id: Batch to delete

        Returns:
            Deleted batch

        Raises:
            BatchNotFoundError: Batch doesn't exist
            BatchDeletedError: Batch already deleted
        """
        batch = self.get_by_id(batch_id, include_deleted=True)

        if batch.is_deleted:
            raise BatchDeletedError(batch_id=batch_id)

        batch.deleted_at = datetime.now(timezone.utc)
        batch.updated_at = datetime.now(timezone.utc)

        self.session.commit()
        self.session.refresh(batch)

        return batch

    # ------------------------------------------------------------------ #
    # Reservation operations                                               #
    # ------------------------------------------------------------------ #

    def create_reservation(
        self,
        batch_id: int,
        reserved_qty: float,
        purpose: str | None = None,
    ) -> BatchReservation:
        """
        Reserve liters from a batch for production planning (pessimistic locking).

        Uses SELECT FOR UPDATE to prevent over-reservation under concurrency.

        Args:
            batch_id: Batch to reserve from
            reserved_qty: Liters to reserve
            purpose: Human-readable reason for the reservation

        Returns:
            Created BatchReservation

        Raises:
            BatchNotFoundError: Batch doesn't exist
            BatchDeletedError: Batch is soft-deleted
            BatchExpiredError: Batch has expired
            InsufficientVolumeError: Not enough free (unreserved) volume
        """
        # Acquire pessimistic lock on batch
        statement = select(Batch).where(Batch.id == batch_id).with_for_update()
        batch = self.session.exec(statement).first()

        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        if batch.is_deleted:
            raise BatchDeletedError(batch_id=batch_id)

        if batch.is_expired:
            raise BatchExpiredError(batch_id=batch_id, expiry_date=batch.expiry_date)

        free = batch.free_liters
        if reserved_qty > free:
            raise InsufficientVolumeError(
                batch_id=batch_id,
                available=free,
                requested=reserved_qty,
            )

        reservation = BatchReservation(
            batch_id=batch_id,
            reserved_qty=reserved_qty,
            purpose=purpose,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)

        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> BatchReservation:
        """
        Retrieve a reservation by its ID.

        Args:
            reservation_id: Reservation ID

        Returns:
            BatchReservation instance

        Raises:
            ReservationNotFoundError: Reservation doesn't exist
        """
        reservation = self.session.get(BatchReservation, reservation_id)
        if not reservation:
            raise ReservationNotFoundError(reservation_id=reservation_id)
        return reservation

    def list_reservations(self, batch_id: int) -> List[BatchReservation]:
        """
        List all reservations for a batch (active and released).

        Args:
            batch_id: Batch ID

        Returns:
            List of BatchReservation records ordered by reserved_at desc
        """
        statement = (
            select(BatchReservation)
            .where(BatchReservation.batch_id == batch_id)
            .order_by(BatchReservation.reserved_at.desc())  # type: ignore[union-attr]
        )
        return list(self.session.exec(statement).all())

    def release_reservation(self, reservation_id: int) -> BatchReservation:
        """
        Release an active reservation.

        Args:
            reservation_id: Reservation to release

        Returns:
            Updated BatchReservation

        Raises:
            ReservationNotFoundError: Reservation doesn't exist
            ReservationAlreadyReleasedError: Reservation already released
        """
        reservation = self.get_reservation_by_id(reservation_id)

        if not reservation.is_active:
            raise ReservationAlreadyReleasedError(reservation_id=reservation_id)

        reservation.released_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(reservation)

        return reservation
