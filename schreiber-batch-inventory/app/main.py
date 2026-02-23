"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.config import settings
from app.logging_config import configure_logging
from app.middleware import CorrelationIdMiddleware


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Configure application resources on startup."""
    configure_logging(log_level=settings.log_level)
    yield


app = FastAPI(
    title="Schreiber Foods Batch Inventory API",
    description="Batch inventory and shelf-life tracking system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Attach correlation ID middleware (must be added before routes)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(api_v1_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
