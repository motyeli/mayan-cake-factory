"""Test configuration.

Unit tests must never touch the network. The environment is pinned to mock
mode with dummy credentials here so a missing .env cannot silently turn a
unit test into an integration test.
"""

import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AI_MODE", "mock")
os.environ.setdefault("MAPS_PROVIDER", "mock")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()
