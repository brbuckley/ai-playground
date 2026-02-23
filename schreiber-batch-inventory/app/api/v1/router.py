"""Main router aggregator for API v1."""

from fastapi import APIRouter

from app.api.v1.batches import router as batches_router

router = APIRouter(prefix="/api")

router.include_router(batches_router)
