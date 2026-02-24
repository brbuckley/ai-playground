"""Structured logging configuration with correlation ID support."""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

# Context variable to store the current request's correlation ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "N/A") or "N/A",
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_entry)


class CorrelationIdFilter(logging.Filter):
    """Injects the current request's correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


def configure_logging(log_level: str = "INFO") -> None:
    """
    Set up structured JSON logging with correlation ID support.

    Idempotent: only adds the JSON handler once; subsequent calls only update
    the log level, leaving existing handlers (e.g. pytest's capture handler)
    intact.

    Args:
        log_level: Logging level string (e.g. "INFO", "DEBUG", "WARNING").
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Only install our handler if a JsonFormatter isn't already attached
    already_configured = any(
        isinstance(h.formatter, JsonFormatter)
        for h in root_logger.handlers
        if h.formatter is not None
    )
    if already_configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    root_logger.addHandler(handler)
