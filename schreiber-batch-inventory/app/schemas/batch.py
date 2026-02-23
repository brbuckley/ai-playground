"""Pydantic schemas for batch API requests and responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class BatchCreateRequest(BaseModel):
    """Request schema for creating a batch."""

    batch_code: str = Field(
        pattern=r"^SCH-\d{8}-\d{4}$",
        description="Batch code (format: SCH-YYYYMMDD-XXXX)",
        examples=["SCH-20251204-0001"],
    )
    received_at: datetime = Field(
        description="Receipt timestamp",
    )
    shelf_life_days: int = Field(
        ge=1,
        le=30,
        default=7,
        description="Shelf life in days (1-30)",
    )
    volume_liters: float = Field(
        gt=0,
        description="Total volume in liters",
    )
    fat_percent: float = Field(
        ge=0,
        le=100,
        description="Fat content percentage",
    )


class BatchResponse(BaseModel):
    """Response schema for batch details."""

    id: int
    batch_code: str
    received_at: datetime
    shelf_life_days: int
    expiry_date: datetime
    volume_liters: float
    available_liters: float
    fat_percent: float
    version: int
    is_expired: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConsumeRequest(BaseModel):
    """Request schema for consuming from a batch."""

    qty: float = Field(
        gt=0,
        description="Quantity to consume in liters",
    )
    order_id: str | None = Field(
        default=None,
        max_length=100,
        description="Associated production order ID",
    )


class ConsumeResponse(BaseModel):
    """Response schema for consumption operation."""

    batch_id: int
    qty_consumed: float
    available_liters: float
    order_id: str | None
    consumed_at: datetime


class BatchListResponse(BaseModel):
    """Response schema for batch list."""

    batches: list[BatchResponse]
    total: int
