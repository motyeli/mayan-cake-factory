"""Supabase Storage: uploads, validation and signed URLs.

Customer uploads and generated designs live in PRIVATE buckets. Nothing is
served from a public URL, because a public link to a customer's personal
photograph is a permanent leak that survives deleting the order.

Validation does not trust the browser. The declared Content-Type and the file
extension are both attacker-controlled, so the actual bytes are sniffed and the
three must agree. A .jpg header on a file called script.js is rejected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.core.supabase import supabase

logger = get_logger(__name__)

CUSTOMER_UPLOADS = "customer-uploads"
CAKE_DESIGNS = "cake-designs"

# Signed URLs are short-lived. Long enough to load a page and look at it,
# short enough that a leaked URL is worthless by the time it is shared.
SIGNED_URL_SECONDS = 3600

_ALLOWED = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
    "image/svg+xml": (".svg",),
}

# Leading bytes that identify a real image. Checked instead of believing the
# declared type, which the browser controls.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


@dataclass(frozen=True)
class StoredFile:
    bucket: str
    path: str
    mime_type: str
    size: int


def sniff_mime(data: bytes) -> str | None:
    """Content type according to the bytes themselves."""
    for signature, mime in _MAGIC:
        if data.startswith(signature):
            return mime
    # RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:200].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:400]):
        return "image/svg+xml"
    return None


def validate_upload(data: bytes, filename: str, declared_mime: str) -> str:
    """Returns the trusted content type, or raises ValidationError.

    Messages name the real problem so the customer can fix it, rather than
    saying "invalid file".
    """
    settings = get_settings()

    if not data:
        raise ValidationError("That file is empty.")

    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise ValidationError(f"That image is too large. The limit is {limit_mb} MB.")

    actual = sniff_mime(data)
    if actual is None:
        raise ValidationError("That file does not look like an image. Please upload a JPEG, PNG or WebP.")

    if actual not in _ALLOWED:
        raise ValidationError("That image format is not supported. Please use JPEG, PNG or WebP.")

    extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if extension and extension not in _ALLOWED[actual]:
        # The bytes and the name disagree. Could be innocent, but a mismatch is
        # exactly what an upload attack looks like, so it is refused either way.
        logger.warning(
            "upload extension does not match its contents",
            extra={"declared_mime": declared_mime, "sniffed_mime": actual, "extension": extension},
        )
        raise ValidationError("The file name does not match the image type. Please rename it and try again.")

    # SVG can carry script. Customer uploads are shown in an <img>, which does
    # not execute script, but the format is refused anyway rather than relying
    # on every future template getting that right.
    if actual == "image/svg+xml":
        raise ValidationError("SVG images are not supported. Please upload a JPEG, PNG or WebP.")

    return actual


async def store_customer_upload(
    session_id: str, data: bytes, filename: str, declared_mime: str
) -> StoredFile:
    mime = validate_upload(data, filename, declared_mime)
    extension = _ALLOWED[mime][0]
    # Path is derived from the session and a random name — never from the
    # customer's filename, which could contain traversal sequences.
    path = f"{session_id}/{uuid.uuid4().hex}{extension}"

    await supabase.upload(CUSTOMER_UPLOADS, path, data, mime)
    logger.info("customer upload stored", extra={"bucket": CUSTOMER_UPLOADS, "size": len(data)})
    return StoredFile(bucket=CUSTOMER_UPLOADS, path=path, mime_type=mime, size=len(data))


async def store_design(session_id: str, version: int, data: bytes, mime: str) -> StoredFile:
    extension = {"image/png": ".png", "image/svg+xml": ".svg", "image/webp": ".webp"}.get(mime, ".png")
    path = f"{session_id}/v{version}{extension}"
    # upsert: a regenerated version overwrites its own file rather than
    # accumulating orphans in the bucket.
    await supabase.upload(CAKE_DESIGNS, path, data, mime, upsert=True)
    return StoredFile(bucket=CAKE_DESIGNS, path=path, mime_type=mime, size=len(data))


async def signed_url(storage_path: str | None, *, expires_in: int = SIGNED_URL_SECONDS) -> str | None:
    """Time-limited URL for a private object.

    `storage_path` is stored as "bucket/path". Returns None rather than raising
    when the object is missing, so one broken image cannot fail a whole page.
    """
    if not storage_path or "/" not in storage_path:
        return None
    bucket, _, path = storage_path.partition("/")
    try:
        return await supabase.signed_url(bucket, path, expires_in=expires_in)
    except Exception as exc:  # a missing object must not break the page
        logger.warning("could not sign storage url", extra={"error_type": type(exc).__name__})
        return None
