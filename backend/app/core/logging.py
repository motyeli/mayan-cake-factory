"""Structured JSON logging with request correlation.

Spec section 50 lists what must be logged and what must never be. The
never-list is enforced here rather than left to reviewer discipline: any key
whose name looks like a secret is redacted on the way out, so a careless
`logger.info("...", extra={"api_key": key})` cannot leak.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar

from app.core.config import get_settings

# Set per request by CorrelationIdMiddleware; read by the formatter.
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

# Substrings that mark a field as never-loggable (spec section 50).
_REDACT = (
    "api_key", "apikey", "secret", "token", "password", "authorization",
    "service_role", "anon_key", "credential", "signed_url", "signature",
)

_REDACTED = "[redacted]"

# Standard LogRecord attributes, so anything else in __dict__ is ours.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "asctime", "message", "taskName",
}


def _scrub(key: str, value: object) -> object:
    lowered = key.lower()
    if any(marker in lowered for marker in _REDACT):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _scrub(k, v) for k, v in value.items()}
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line — Railway's log viewer parses these natively."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
            "env": get_settings().app_env,
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = _scrub(key, value)

        if record.exc_info:
            # Type and message only. A traceback can contain request bodies.
            exc_type, exc_value, _ = record.exc_info
            payload["error_type"] = exc_type.__name__ if exc_type else "Unknown"
            payload["error_message"] = str(exc_value)[:500]

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(get_settings().log_level.upper())

    # uvicorn duplicates access logs in its own format; route them through ours.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def get_logger(name: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(name), {})
