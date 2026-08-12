"""Frontend service tests: routing, template rendering and accessibility basics.

The accessibility assertions are on rendered HTML. That catches the failures
that actually recur (missing landmarks, unlabelled inputs, no skip link); it
is not a substitute for a real audit, and the README says so.
"""

import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_healthz(client):
    body = client.get("/healthz").get_json()
    assert body["status"] == "ok"
    assert body["service"] == "frontend"


def test_home_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Design Your Cake" in response.data


def test_backend_url_is_injected_not_hardcoded(client):
    html = client.get("/").get_data(as_text=True)
    assert 'data-backend-url="http://localhost:8001"' in html


def test_no_secrets_reach_the_page(client):
    html = client.get("/").get_data(as_text=True).lower()
    for marker in ("service_role", "sb_secret", "apikey", "secret_key", "eyj"):
        assert marker not in html, f"{marker} appeared in delivered HTML"


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("fragment", [
    '<html lang="en">',      # language declared for screen readers
    'class="skip-link"',     # keyboard users can bypass the header
    "<main id=\"main\">",    # single main landmark
    'aria-label="Primary"',  # nav is identifiable
    'role="status"',         # async loading is announced
])
def test_accessibility_basics(client, fragment):
    assert fragment in client.get("/").get_data(as_text=True)
