"""Guest design sessions and their access tokens.

Customers never create an account (spec section 6). A session is reached
through a secure link, and only the SHA-256 hash of the token is stored — a
database leak yields hashes, not working links.

The token is returned exactly once, when the session is created. There is no
endpoint that can retrieve it again, because there is nothing to retrieve.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.core.errors import ConflictError, NotFoundError
from app.core.supabase import supabase

# 32 bytes of urlsafe randomness. Guessing is not a threat model at this size.
TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(*, expires_days: int = 14, ip_hash: str | None = None) -> tuple[str, dict]:
    """Returns (plaintext_token, session_row). The token is never stored."""
    token = new_token()
    expires_at = datetime.now(UTC) + timedelta(days=expires_days)

    rows = await supabase.insert(
        "design_sessions",
        {
            "public_token_hash": hash_token(token),
            "status": "active",
            "expires_at": expires_at.isoformat(),
            "ip_hash": ip_hash,
        },
    )
    return token, rows[0]


async def get_session(token: str) -> dict:
    """Look a session up by token, rejecting expired ones.

    Expiry is checked here rather than by a cleanup job so a link stops working
    the moment it should, whether or not anything has swept the table.
    """
    rows, _ = await supabase.select(
        "design_sessions", filters={"public_token_hash": f"eq.{hash_token(token)}"}, limit=1
    )
    if not rows:
        raise NotFoundError("That design link is not valid.")

    session = rows[0]
    expires_at = datetime.fromisoformat(session["expires_at"])
    if expires_at <= datetime.now(UTC):
        raise ConflictError(
            "That design link has expired. You are welcome to start a new design.",
            {"reason": "SESSION_EXPIRED"},
        )
    return session


async def touch(session_id: str, **fields) -> None:
    payload = {"last_seen_at": datetime.now(UTC).isoformat(), **fields}
    await supabase.update("design_sessions", filters={"id": f"eq.{session_id}"}, payload=payload)


async def get_specification_row(session_id: str) -> dict | None:
    rows, _ = await supabase.select(
        "cake_specifications", filters={"session_id": f"eq.{session_id}"}, limit=1
    )
    return rows[0] if rows else None


async def save_specification(session_id: str, payload: dict) -> dict:
    """Upsert the specification for a session.

    One row per session (enforced by a unique constraint), so the running
    specification is a single mutable record rather than an append-only log —
    the design VERSIONS carry the history instead.
    """
    existing = await get_specification_row(session_id)
    if existing:
        rows = await supabase.update(
            "cake_specifications", filters={"id": f"eq.{existing['id']}"}, payload=payload
        )
    else:
        rows = await supabase.insert("cake_specifications", {"session_id": session_id, **payload})
    return rows[0]


async def append_message(
    session_id: str,
    *,
    role: str,
    message: str,
    structured_data: dict | None = None,
    provider: str | None = None,
    provider_message_id: str | None = None,
    usage: dict | None = None,
    error_info: str | None = None,
) -> None:
    await supabase.insert(
        "ai_conversations",
        {
            "session_id": session_id,
            "role": role,
            "message": message,
            "structured_data": structured_data,
            "provider": provider,
            "provider_message_id": provider_message_id,
            # Token counts and latency only — never prompt or reply text, which
            # is already stored once in `message`.
            "usage_metadata": usage,
            "error_info": error_info,
        },
    )


async def load_messages(session_id: str, limit: int = 40) -> list[dict]:
    rows, _ = await supabase.select(
        "ai_conversations",
        columns="role,message,created_at",
        filters={"session_id": f"eq.{session_id}"},
        order="created_at",
        limit=limit,
    )
    return rows
