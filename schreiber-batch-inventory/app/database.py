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
