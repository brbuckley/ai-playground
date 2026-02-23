"""Domain-specific exception classes."""


class BatchInventoryError(Exception):
    """Base exception for batch inventory errors."""

    pass


class BatchNotFoundError(BatchInventoryError):
    """Raised when batch cannot be found."""

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        super().__init__(f"Batch with ID {batch_id} not found")


class BatchDeletedError(BatchInventoryError):
    """Raised when attempting to operate on a deleted batch."""

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        super().__init__(f"Batch {batch_id} has been deleted")


class BatchExpiredError(BatchInventoryError):
    """Raised when attempting to consume from an expired batch."""

    def __init__(self, batch_id: int, expiry_date: object):
        self.batch_id = batch_id
        self.expiry_date = expiry_date
        super().__init__(f"Batch {batch_id} expired on {expiry_date}")


class InsufficientVolumeError(BatchInventoryError):
    """Raised when requested consumption exceeds available volume."""

    def __init__(self, batch_id: int, available: float, requested: float):
        self.batch_id = batch_id
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient volume in batch {batch_id}: "
            f"available={available}L, requested={requested}L"
        )


class DuplicateBatchCodeError(BatchInventoryError):
    """Raised when batch_code already exists."""

    def __init__(self, batch_code: str):
        self.batch_code = batch_code
        super().__init__(f"Batch code '{batch_code}' already exists")


class ReservationNotFoundError(BatchInventoryError):
    """Raised when a reservation cannot be found."""

    def __init__(self, reservation_id: int):
        self.reservation_id = reservation_id
        super().__init__(f"Reservation with ID {reservation_id} not found")


class ReservationAlreadyReleasedError(BatchInventoryError):
    """Raised when attempting to release an already-released reservation."""

    def __init__(self, reservation_id: int):
        self.reservation_id = reservation_id
        super().__init__(f"Reservation {reservation_id} has already been released")
