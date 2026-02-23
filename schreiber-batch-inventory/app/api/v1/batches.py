"""API endpoints for batch operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.database import get_session
from app.domain.exceptions import (
    BatchDeletedError,
    BatchExpiredError,
    BatchNotFoundError,
    DuplicateBatchCodeError,
    InsufficientVolumeError,
)
from app.domain.services.batch_service import BatchService
from app.schemas.batch import (
    BatchCreateRequest,
    BatchListResponse,
    BatchResponse,
    ConsumeRequest,
    ConsumeResponse,
)

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("/", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    batch_data: BatchCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> BatchResponse:
    """Create a new batch."""
    service = BatchService(session)

    try:
        batch = service.create_batch(
            batch_code=batch_data.batch_code,
            received_at=batch_data.received_at,
            shelf_life_days=batch_data.shelf_life_days,
            volume_liters=batch_data.volume_liters,
            fat_percent=batch_data.fat_percent,
        )
        return BatchResponse.model_validate(batch)

    except DuplicateBatchCodeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get("/near-expiry", response_model=BatchListResponse)
def get_near_expiry_batches(
    n_days: int = Query(..., ge=1, le=365, description="Look-ahead window in days"),
    session: Annotated[Session, Depends(get_session)] = None,
) -> BatchListResponse:
    """Get batches nearing expiry with available volume."""
    service = BatchService(session)
    batches = service.get_near_expiry_batches(n_days=n_days)

    return BatchListResponse(
        batches=[BatchResponse.model_validate(b) for b in batches],
        total=len(batches),
    )


@router.get("/", response_model=BatchListResponse)
def list_batches(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    session: Annotated[Session, Depends(get_session)] = None,
) -> BatchListResponse:
    """List active (non-deleted) batches."""
    service = BatchService(session)
    batches = service.list_batches(skip=skip, limit=limit)

    return BatchListResponse(
        batches=[BatchResponse.model_validate(b) for b in batches],
        total=len(batches),
    )


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(
    batch_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> BatchResponse:
    """Retrieve a batch by ID."""
    service = BatchService(session)

    try:
        batch = service.get_batch(batch_id)
        return BatchResponse.model_validate(batch)

    except BatchNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/{batch_id}/consume", response_model=ConsumeResponse)
def consume_batch(
    batch_id: int,
    consume_data: ConsumeRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ConsumeResponse:
    """Consume liters from a batch (atomic operation)."""
    service = BatchService(session)

    try:
        record = service.consume_from_batch(
            batch_id=batch_id,
            qty=consume_data.qty,
            order_id=consume_data.order_id,
        )

        # Get updated batch to calculate available liters
        batch = service.get_batch(batch_id)

        return ConsumeResponse(
            batch_id=record.batch_id,
            qty_consumed=record.qty,
            available_liters=batch.available_liters,
            order_id=record.order_id,
            consumed_at=record.consumed_at,
        )

    except BatchNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except (BatchDeletedError, BatchExpiredError, InsufficientVolumeError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Soft-delete a batch."""
    service = BatchService(session)

    try:
        service.delete_batch(batch_id)
    except BatchNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except BatchDeletedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
