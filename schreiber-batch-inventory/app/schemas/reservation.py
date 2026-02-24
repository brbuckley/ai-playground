"""Pydantic schemas for batch reservation API requests and responses."""

from datetime import datetime, timezone

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class ReserveRequest(BaseModel):
    """Request schema for reserving liters from a batch."""

    reserved_qty: float = Field(
        gt=0,
        description="Quantity to reserve in liters",
    )
    purpose: str | None = Field(
        default=None,
        max_length=200,
        description="Human-readable reason (e.g. production run ID)",
    )


class ReservationResponse(BaseModel):
    """Response schema for a single reservation."""

    id: int
    batch_id: int
    reserved_qty: float
    purpose: str | None
    reserved_at: AwareDatetime
    released_at: AwareDatetime | None
    is_active: bool

    model_config = {"from_attributes": True}

    @field_validator("reserved_at", mode="before")
    @classmethod
    def ensure_reserved_at_tz(cls, v: datetime) -> datetime:
        """Ensure datetime has timezone info, defaulting to UTC if naive."""
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @field_validator("released_at", mode="before")
    @classmethod
    def ensure_released_at_tz(cls, v: datetime | None) -> datetime | None:
        """Ensure datetime has timezone info, defaulting to UTC if naive."""
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class ReservationListResponse(BaseModel):
    """Response schema for listing reservations."""

    reservations: list[ReservationResponse]
    total: int
