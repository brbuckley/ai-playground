"""SQLModel database models for Batch and ConsumptionRecord."""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    pass


class Batch(SQLModel, table=True):
    """
    Represents a milk delivery batch.

    Business Rules:
    - batch_code must be unique and match pattern SCH-YYYYMMDD-XXXX
    - expiry_date is computed as received_at + shelf_life_days
    - version is incremented on each consumption (optimistic locking support)
    - deleted_at enables soft delete functionality
    """

    __tablename__ = "batches"

    # Primary Key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Business Identifiers
    batch_code: str = Field(
        unique=True,
        index=True,
        max_length=20,
        description="Unique batch identifier (SCH-YYYYMMDD-XXXX)",
    )

    # Batch Properties
    received_at: datetime = Field(
        index=True,
        description="Timestamp when batch was received",
    )
    shelf_life_days: int = Field(
        ge=1,
        le=30,
        default=7,
        description="Shelf life duration (1-30 days)",
    )
    expiry_date: datetime = Field(
        index=True,
        description="Computed expiry date (received_at + shelf_life_days)",
    )
    volume_liters: float = Field(
        ge=0,
        description="Total volume in liters",
    )
    fat_percent: float = Field(
        ge=0,
        le=100,
        description="Fat content percentage",
    )

    # Concurrency Control
    version: int = Field(
        default=1,
        description="Version number for optimistic locking",
    )

    # Soft Delete
    deleted_at: Optional[datetime] = Field(
        default=None,
        index=True,
        description="Timestamp of soft deletion (NULL if active)",
    )

    # Audit Trail
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record last update timestamp",
    )

    # Relationships
    consumption_records: list["ConsumptionRecord"] = Relationship(
        back_populates="batch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @property
    def available_liters(self) -> float:
        """
        Calculate available volume.

        Returns:
            Total volume minus sum of all consumption records.
        """
        if not self.consumption_records:
            return self.volume_liters

        total_consumed = sum(record.qty for record in self.consumption_records)
        return max(0.0, self.volume_liters - total_consumed)

    @property
    def is_expired(self) -> bool:
        """Check if batch has passed expiry date."""
        # Ensure expiry_date is timezone-aware for comparison
        expiry = self.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expiry

    @property
    def is_deleted(self) -> bool:
        """Check if batch is soft-deleted."""
        return self.deleted_at is not None

    @classmethod
    def create(
        cls,
        batch_code: str,
        received_at: datetime,
        shelf_life_days: int,
        volume_liters: float,
        fat_percent: float,
    ) -> "Batch":
        """
        Factory method to create a new batch with computed expiry date.

        Args:
            batch_code: Unique batch identifier
            received_at: Receipt timestamp
            shelf_life_days: Shelf life duration (1-30)
            volume_liters: Total volume
            fat_percent: Fat content percentage

        Returns:
            New Batch instance with expiry_date computed
        """
        expiry_date = received_at + timedelta(days=shelf_life_days)
        return cls(
            batch_code=batch_code,
            received_at=received_at,
            shelf_life_days=shelf_life_days,
            expiry_date=expiry_date,
            volume_liters=volume_liters,
            fat_percent=fat_percent,
        )


class ConsumptionRecord(SQLModel, table=True):
    """
    Represents a consumption event from a batch.

    Each record tracks:
    - How much was consumed (qty)
    - Associated production order (order_id)
    - When consumption occurred (consumed_at)
    """

    __tablename__ = "consumption_records"

    # Primary Key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Foreign Key
    batch_id: int = Field(
        foreign_key="batches.id",
        index=True,
        description="Reference to parent batch",
    )

    # Consumption Details
    qty: float = Field(
        gt=0,
        description="Quantity consumed in liters",
    )
    order_id: Optional[str] = Field(
        default=None,
        max_length=100,
        index=True,
        description="Associated production order ID",
    )

    # Audit Trail
    consumed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
        description="Timestamp of consumption",
    )

    # Relationships
    batch: Optional[Batch] = Relationship(back_populates="consumption_records")
