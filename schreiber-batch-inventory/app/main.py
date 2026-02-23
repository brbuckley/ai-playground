"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router

app = FastAPI(
    title="Schreiber Foods Batch Inventory API",
    description="Batch inventory and shelf-life tracking system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(api_v1_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
