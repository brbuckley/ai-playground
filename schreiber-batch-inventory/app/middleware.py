"""FastAPI middleware for cross-cutting concerns."""

import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import correlation_id_var


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches a correlation ID to every request.

    - Reads ``X-Correlation-ID`` from incoming headers (if present).
    - Generates a new UUID v4 when the header is absent.
    - Stores the ID in a ``ContextVar`` so it is accessible from any log
      statement made during the request lifecycle.
    - Echoes the correlation ID back in the response headers.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)
