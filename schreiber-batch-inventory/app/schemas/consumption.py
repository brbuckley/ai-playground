"""Pydantic schemas for consumption API requests and responses."""

from datetime import datetime, timezone

from pydantic import AwareDatetime, BaseModel, field_validator


class ConsumptionRecordResponse(BaseModel):
    """Response schema for a consumption record."""

    id: int
    batch_id: int
    qty: float
    order_id: str | None
    consumed_at: AwareDatetime

    model_config = {"from_attributes": True}

    @field_validator("consumed_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        """Ensure datetime has timezone info, defaulting to UTC if naive."""
        if value and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
