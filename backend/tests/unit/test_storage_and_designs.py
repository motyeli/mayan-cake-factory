"""Upload validation and revision-limit enforcement.

Both are places where trusting the client costs something real: an unchecked
upload is a security hole, and an unenforced revision limit is the bakery
paying for image generation without bound.
"""

from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.services.storage import sniff_mime, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


# ------------------------------------------------------------------ sniffing

@pytest.mark.parametrize(
    ("data", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"),
     (WEBP, "image/webp"), (SVG, "image/svg+xml"), (b"not an image at all", None)],
)
def test_content_type_comes_from_the_bytes(data, expected):
    assert sniff_mime(data) == expected


# ---------------------------------------------------------------- validation

def test_a_real_png_is_accepted():
    assert validate_upload(PNG, "inspiration.png", "image/png") == "image/png"


def test_jpg_and_jpeg_extensions_both_work():
    assert validate_upload(JPEG, "cake.jpg", "image/jpeg") == "image/jpeg"
    assert validate_upload(JPEG, "cake.jpeg", "image/jpeg") == "image/jpeg"


def test_the_declared_type_is_not_trusted():
    """A browser can claim anything; the bytes decide."""
    with pytest.raises(ValidationError):
        validate_upload(b"#!/bin/sh\nrm -rf /", "payload.png", "image/png")


def test_extension_must_match_the_actual_contents():
    """PNG bytes named .jpg — innocent or not, a mismatch is refused."""
    with pytest.raises(ValidationError, match="does not match"):
        validate_upload(PNG, "sneaky.jpg", "image/png")


def test_svg_is_refused_because_it_can_carry_script():
    with pytest.raises(ValidationError, match="SVG"):
        validate_upload(SVG, "logo.svg", "image/svg+xml")


def test_gif_is_refused_as_an_unsupported_format():
    with pytest.raises(ValidationError):
        validate_upload(GIF, "animation.gif", "image/gif")


def test_empty_file_is_refused():
    with pytest.raises(ValidationError, match="empty"):
        validate_upload(b"", "nothing.png", "image/png")


def test_oversized_file_is_refused_with_the_limit_named():
    from app.core.config import get_settings

    oversized = PNG + b"\x00" * get_settings().max_upload_bytes
    with pytest.raises(ValidationError, match="too large"):
        validate_upload(oversized, "huge.png", "image/png")


def test_a_file_with_no_extension_is_judged_on_its_bytes():
    assert validate_upload(PNG, "screenshot", "image/png") == "image/png"


# ------------------------------------------------------- revision allowance

class _Session(dict):
    pass


@pytest.mark.asyncio
async def test_revision_limit_is_enforced_in_the_backend(monkeypatch):
    """The frontend counter is a courtesy. This is the control, because each
    generation costs the bakery money."""
    from app.core.errors import ConflictError
    from app.services import designs

    async def fake_settings():
        return {"max_revisions": 3}

    monkeypatch.setattr(designs, "load_settings", fake_settings)

    assert await designs.check_revision_allowance(_Session(revision_count=0)) == 3
    assert await designs.check_revision_allowance(_Session(revision_count=2)) == 1

    with pytest.raises(ConflictError) as exc:
        await designs.check_revision_allowance(_Session(revision_count=3))
    assert exc.value.details["reason"] == "REVISION_LIMIT_REACHED"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_the_limit_message_offers_a_way_forward(monkeypatch):
    """Spec section 21: after three revisions the customer can pick an earlier
    version, start again, or ask for a manual review — not just be refused."""
    from app.core.errors import ConflictError
    from app.services import designs

    async def fake_settings():
        return {"max_revisions": 3}

    monkeypatch.setattr(designs, "load_settings", fake_settings)

    with pytest.raises(ConflictError) as exc:
        await designs.check_revision_allowance(_Session(revision_count=5))
    message = exc.value.message.lower()
    assert "earlier version" in message
    assert "start a new design" in message


@pytest.mark.asyncio
async def test_the_limit_is_configurable(monkeypatch):
    """Mayan can change it from the admin panel without a deployment."""
    from app.services import designs

    async def fake_settings():
        return {"max_revisions": 5}

    monkeypatch.setattr(designs, "load_settings", fake_settings)
    assert await designs.check_revision_allowance(_Session(revision_count=4)) == 1
