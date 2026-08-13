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


# ------------------------------------------------------------ design screen

def test_design_page_renders(client):
    assert client.get("/design").status_code == 200


def test_design_page_has_no_external_requests(client):
    """Stitch emits a Tailwind CDN script and a Google Fonts link. Neither can
    ship: section 37 rules out frontend frameworks, and the fonts CDN sends
    visitor IPs to a third party, which is a GDPR problem for a French
    business (AD-12)."""
    html = client.get("/design").get_data(as_text=True)
    for forbidden in ("cdn.tailwindcss.com", "fonts.googleapis.com",
                      "fonts.gstatic.com", "Material+Symbols"):
        assert forbidden not in html, f"{forbidden} would be requested from the page"


def test_home_page_has_no_external_requests(client):
    html = client.get("/").get_data(as_text=True)
    for forbidden in ("cdn.tailwindcss.com", "fonts.googleapis.com"):
        assert forbidden not in html


@pytest.mark.parametrize("fragment", [
    'role="log"',              # the conversation is announced to screen readers
    'aria-live="polite"',      # ...without stealing focus from the input
    'class="visually-hidden" for="message"',   # the textarea has a real label
    'aria-current="step"',     # progress indicator marks where you are
    'data-backend-url',        # API base injected, never hard-coded in JS
])
def test_design_page_accessibility_and_wiring(client, fragment):
    assert fragment in client.get("/design").get_data(as_text=True)


def test_icon_buttons_have_accessible_names(client):
    """Icon-only buttons are invisible to screen readers without a label."""
    html = client.get("/design").get_data(as_text=True)
    assert "Send message" in html
    assert "Attach an inspiration image" in html


def test_summary_page_renders(client):
    assert client.get("/design/summary").status_code == 200


def test_summary_page_has_no_external_requests(client):
    html = client.get("/design/summary").get_data(as_text=True)
    for forbidden in ("cdn.tailwindcss.com", "fonts.googleapis.com", "Material+Symbols"):
        assert forbidden not in html


def test_summary_page_marks_the_confirm_step(client):
    html = client.get("/design/summary").get_data(as_text=True)
    assert 'aria-current="step"' in html
    assert "Create my design" in html
    assert "Keep editing" in html


# ------------------------------------------------------- home page content

def test_home_page_states_no_business_facts_of_its_own():
    """The generated design copy invented a two-week lead time, a 50% credit
    card deposit and a 14-day refund policy — none of which this product has.
    Every business fact must come from the catalog endpoint at runtime, so the
    marketing page cannot contradict the rule engine."""
    import pathlib

    html = pathlib.Path("templates/home.html").read_text(encoding="utf-8")
    for invented in ("2 weeks", "two weeks", "50% deposit", "credit card",
                     "14 days", "Rue Royale", "tasting", "4-6 weeks"):
        assert invented.lower() not in html.lower(), (
            f"'{invented}' is hard-coded in the template instead of coming from settings"
        )


def test_home_page_has_hooks_for_settings_driven_copy(client):
    html = client.get("/").get_data(as_text=True)
    for hook in ("data-lead-time", "data-allergen", "data-payment",
                 "data-cancellation", "data-visual-disclaimer", "data-zones"):
        assert hook in html


def test_hero_image_has_meaningful_alt_text(client):
    html = client.get("/").get_data(as_text=True)
    assert "buttercream" in html and "alt=" in html


# ----------------------------------------------------------- design preview

def test_preview_page_renders(client):
    assert client.get("/design/preview").status_code == 200


def test_preview_shows_staged_progress_not_a_bare_spinner(client):
    """Generation takes about a minute with a real provider. Spec section 51
    requires a clear progress state, not a frozen screen."""
    html = client.get("/design/preview").get_data(as_text=True)
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "about a minute" in html


def test_preview_has_revision_and_approval_controls(client):
    html = client.get("/design/preview").get_data(as_text=True)
    assert "Request this change" in html
    assert "Approve this design" in html
    assert 'for="revision"' in html          # the textarea has a real label


def test_preview_page_has_no_external_requests(client):
    html = client.get("/design/preview").get_data(as_text=True)
    for forbidden in ("cdn.tailwindcss.com", "fonts.googleapis.com", "Material+Symbols"):
        assert forbidden not in html
