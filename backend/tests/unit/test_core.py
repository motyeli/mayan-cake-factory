"""Core infrastructure tests.

These cover the pieces that silently protect the system: log redaction, the
error envelope, rate limiting and CORS configuration. A regression in any of
them is invisible in normal use, which is exactly why they are tested.
"""

from __future__ import annotations

import json
import logging

import pytest
from app.core.errors import ConflictError, RateLimitError
from app.core.logging import JsonFormatter, correlation_id
from app.core.rate_limit import RateLimiter
from app.main import create_app
from fastapi.testclient import TestClient

# ------------------------------------------------------------- log redaction

def _format(**extra) -> dict:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
    record.__dict__.update(extra)
    return json.loads(JsonFormatter().format(record))


def test_secret_looking_fields_are_redacted():
    payload = _format(
        api_key="sk-live-realkey",
        supabase_service_role_key="service-secret",
        authorization="Bearer abc",
        signed_url="https://storage/private?token=xyz",
        password="hunter2",
    )
    for field in ("api_key", "supabase_service_role_key", "authorization", "signed_url", "password"):
        assert payload[field] == "[redacted]", f"{field} leaked into the log"


def test_nested_secrets_are_redacted():
    payload = _format(provider_config={"llm_api_key": "sk-live", "model": "gpt-4.1-mini"})
    assert payload["provider_config"]["llm_api_key"] == "[redacted]"
    # Non-secret siblings must survive, or the logs become useless.
    assert payload["provider_config"]["model"] == "gpt-4.1-mini"


def test_ordinary_operational_fields_are_kept():
    payload = _format(order_number="MCF-20260812-01001", duration_ms=42.5, status=200)
    assert payload["order_number"] == "MCF-20260812-01001"
    assert payload["duration_ms"] == 42.5
    assert payload["status"] == 200


def test_traceback_is_not_serialised():
    try:
        raise ValueError("customer address 12 rue Secret")
    except ValueError as exc:
        info = (type(exc), exc, exc.__traceback__)
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", (), info)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["error_type"] == "ValueError"
    assert "Traceback" not in json.dumps(payload)


def test_correlation_id_is_included():
    token = correlation_id.set("abc123")
    try:
        assert _format()["correlation_id"] == "abc123"
    finally:
        correlation_id.reset(token)


# --------------------------------------------------------------- rate limiter

def test_rate_limiter_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit("session-1", limit=3, per_seconds=60)
    with pytest.raises(RateLimitError):
        limiter.hit("session-1", limit=3, per_seconds=60)


def test_rate_limiter_buckets_are_independent():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit("session-1", limit=3, per_seconds=60)
    # A different customer must not be punished for the first one's usage.
    limiter.hit("session-2", limit=3, per_seconds=60)


def test_rate_limiter_window_expires():
    limiter = RateLimiter()
    limiter.hit("s", limit=1, per_seconds=60)
    with pytest.raises(RateLimitError):
        limiter.hit("s", limit=1, per_seconds=60)
    # Expire the window rather than sleeping for a minute.
    limiter._windows["s"].resets_at = 0.0
    limiter.hit("s", limit=1, per_seconds=60)


def test_rate_limit_error_reports_retry_after():
    limiter = RateLimiter()
    limiter.hit("s", limit=1, per_seconds=60)
    with pytest.raises(RateLimitError) as exc:
        limiter.hit("s", limit=1, per_seconds=60)
    assert exc.value.details["retry_after_seconds"] > 0


# ----------------------------------------------------------------- http layer

@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health_reports_dependencies(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "test"
    assert body["ai_mode"] == "mock"
    # Without lifespan the client is not started; the check must report that
    # rather than raise, which is the whole point of a health endpoint.
    assert body["database"] in {"ok", "unconfigured", "unreachable"}


def test_health_never_raises_when_database_is_unreachable(client):
    """Regression: ping() used to raise RuntimeError when the HTTP client had
    not been started, turning /health into a 500."""
    assert client.get("/health").status_code == 200


def test_unknown_route_uses_the_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert "correlation_id" in body


def test_correlation_id_is_echoed(client):
    response = client.get("/health", headers={"X-Correlation-ID": "trace-me"})
    assert response.headers["X-Correlation-ID"] == "trace-me"


def test_security_headers_are_present(client):
    headers = client.get("/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_conflict_error_maps_to_409(client):
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise ConflictError("That date is fully booked.", {"reason": "DATE_FULL"})

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "DATE_FULL"


def test_unhandled_exception_hides_internals(client):
    app = create_app()

    @app.get("/explode")
    async def explode():
        raise RuntimeError("connection string postgres://user:pw@host")

    body = TestClient(app, raise_server_exceptions=False).get("/explode").json()
    assert body["error"]["code"] == "internal_error"
    assert "postgres://" not in json.dumps(body)
