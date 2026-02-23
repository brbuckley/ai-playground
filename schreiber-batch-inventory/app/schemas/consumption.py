"""Pydantic schemas for consumption API requests and responses."""

from datetime import datetime

from pydantic import BaseModel


class ConsumptionRecordResponse(BaseModel):
    """Response schema for a consumption record."""

    id: int
    batch_id: int
    qty: float
    order_id: str | None
    consumed_at: datetime

    model_config = {"from_attributes": True}
