# Schreiber Foods Batch Inventory — Project Scaffold Guide

This document provides code templates and scaffolding to accelerate implementation of the batch inventory system.

## Table of Contents
1. [Project Initialization](#project-initialization)
2. [Configuration Files](#configuration-files)
3. [Database Models](#database-models)
4. [Repository Layer](#repository-layer)
5. [Domain Services](#domain-services)
6. [API Schemas](#api-schemas)
7. [API Endpoints](#api-endpoints)
8. [Exception Handling](#exception-handling)
9. [Test Fixtures](#test-fixtures)

---

## 1. Project Initialization

### pyproject.toml
```toml
[project]
name = "schreiber-batch-inventory"
version = "0.1.0"
description = "Batch inventory and shelf-life tracking system for Schreiber Foods"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "sqlmodel>=0.0.22",
    "psycopg2-binary>=2.9.9",
    "alembic>=1.13.0",
    "uvicorn[standard]>=0.30.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --strict-markers --tb=short"

[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### .env.example
```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/schreiber_db
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/schreiber_test_db

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
API_WORKERS=4

# Application Settings
LOG_LEVEL=INFO
DEBUG=false

# Database Pool Settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=0
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

---

## 2. Configuration Files

### app/config.py
```python
"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str
    test_database_url: str | None = None
    db_pool_size: int = 20
    db_max_overflow: int = 0
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = 4

    # Application
    log_level: str = "INFO"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
```

### app/database.py
```python
"""Database connection and session management."""

from typing import Generator
from sqlmodel import Session, create_engine
from app.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,  # Verify connections before use
)


def get_session() -> Generator[Session, None, None]:
    """Dependency to provide database session to endpoints."""
    with Session(engine) as session:
        yield session
```

---

## 3. Database Models

### app/domain/models.py
```python
"""SQLModel database models for Batch and ConsumptionRecord."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from typing import List


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
    id: int | None = Field(default=None, primary_key=True)

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
    deleted_at: datetime | None = Field(
        default=None,
        index=True,
        description="Timestamp of soft deletion (NULL if active)",
    )

    # Audit Trail
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record last update timestamp",
    )

    # Relationships
    consumption_records: "List[ConsumptionRecord]" = Relationship(
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
        return datetime.utcnow() > self.expiry_date

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
    id: int | None = Field(default=None, primary_key=True)

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
    order_id: str | None = Field(
        default=None,
        max_length=100,
        index=True,
        description="Associated production order ID",
    )

    # Audit Trail
    consumed_at: datetime = Field(
        default_factory=datetime.utcnow,
        index=True,
        description="Timestamp of consumption",
    )

    # Relationships
    batch: Batch = Relationship(back_populates="consumption_records")
```

---

## 4. Repository Layer

### app/repositories/batch_repository.py
```python
"""Data access layer for Batch operations."""

from datetime import datetime, timedelta
from typing import List
from sqlmodel import Session, select, func
from app.domain.models import Batch, ConsumptionRecord
from app.domain.exceptions import (
    BatchNotFoundError,
    BatchDeletedError,
    BatchExpiredError,
    InsufficientVolumeError,
    DuplicateBatchCodeError,
)


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
            statement = statement.where(Batch.deleted_at.is_(None))

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
            .where(Batch.deleted_at.is_(None))
            .order_by(Batch.created_at.desc())
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
        threshold = datetime.utcnow() + timedelta(days=n_days)

        statement = (
            select(Batch)
            .where(
                Batch.deleted_at.is_(None),
                Batch.expiry_date <= threshold,
            )
            .order_by(Batch.expiry_date.asc())
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
        batch.updated_at = datetime.utcnow()

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

        batch.deleted_at = datetime.utcnow()
        batch.updated_at = datetime.utcnow()

        self.session.commit()
        self.session.refresh(batch)

        return batch
```

---

## 5. Domain Services

### app/domain/services/batch_service.py
```python
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
```

---

## 6. API Schemas

### app/schemas/batch.py
```python
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
```

---

## 7. API Endpoints

### app/api/v1/batches.py
```python
"""API endpoints for batch operations."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session
from app.database import get_session
from app.domain.services.batch_service import BatchService
from app.domain.exceptions import (
    BatchNotFoundError,
    BatchDeletedError,
    BatchExpiredError,
    InsufficientVolumeError,
    DuplicateBatchCodeError,
)
from app.schemas.batch import (
    BatchCreateRequest,
    BatchResponse,
    ConsumeRequest,
    ConsumeResponse,
    BatchListResponse,
)

router = APIRouter(prefix="/api/batches", tags=["batches"])


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


@router.get("/", response_model=BatchListResponse)
def list_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: Annotated[Session, Depends(get_session)] = None,
) -> BatchListResponse:
    """List active batches."""
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
    """Consume liters from a batch."""
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


@router.get("/near-expiry", response_model=BatchListResponse)
def get_near_expiry_batches(
    n_days: int = Query(..., ge=1, le=30),
    session: Annotated[Session, Depends(get_session)] = None,
) -> BatchListResponse:
    """Get batches nearing expiry."""
    service = BatchService(session)
    batches = service.get_near_expiry_batches(n_days=n_days)

    return BatchListResponse(
        batches=[BatchResponse.model_validate(b) for b in batches],
        total=len(batches),
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
```

---

## 8. Exception Handling

### app/domain/exceptions.py
```python
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
    """Raised when attempting to operate on deleted batch."""

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        super().__init__(f"Batch {batch_id} has been deleted")


class BatchExpiredError(BatchInventoryError):
    """Raised when attempting to consume from expired batch."""

    def __init__(self, batch_id: int, expiry_date):
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
```

---

## 9. Test Fixtures

### tests/conftest.py
```python
"""Pytest fixtures for testing."""

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_session


@pytest.fixture(name="session")
def session_fixture():
    """Create a fresh in-memory database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """Create test client with overridden database session."""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()
```

### tests/integration/test_batch_api.py
```python
"""Integration tests for batch API."""

from datetime import datetime, timedelta
from fastapi.testclient import TestClient


def test_create_batch(client: TestClient):
    """Test creating a new batch."""
    response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0001",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["batch_code"] == "SCH-20251204-0001"
    assert data["available_liters"] == 1000.0
    assert data["version"] == 1


def test_consume_batch(client: TestClient):
    """Test happy path: create and consume."""
    # Create batch
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0002",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 1000.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    # Consume
    consume_response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 250.0, "order_id": "ORDER-001"},
    )

    assert consume_response.status_code == 200
    data = consume_response.json()
    assert data["qty_consumed"] == 250.0
    assert data["available_liters"] == 750.0


def test_over_consumption(client: TestClient):
    """Test consuming more than available."""
    # Create batch with 100L
    create_response = client.post(
        "/api/batches/",
        json={
            "batch_code": "SCH-20251204-0003",
            "received_at": "2025-12-04T08:30:00Z",
            "shelf_life_days": 7,
            "volume_liters": 100.0,
            "fat_percent": 3.5,
        },
    )
    batch_id = create_response.json()["id"]

    # Try to consume 150L
    consume_response = client.post(
        f"/api/batches/{batch_id}/consume",
        json={"qty": 150.0},
    )

    assert consume_response.status_code == 409
    assert "insufficient" in consume_response.json()["detail"].lower()
```

---

**End of Scaffold Guide**

Use these templates as a starting point. Adapt as needed for specific requirements.
