"""Administrator authentication and authorisation.

Login is proxied server-side: the browser posts credentials here, the backend
performs the Supabase password grant and returns the JWT. The browser never
holds the anon key and never talks to the auth service directly.

Tokens are verified by asking Supabase who they belong to, rather than
checking a signature locally. That works whether the project signs with a
shared secret or asymmetric keys, and needs no key-rotation handling — at the
cost of one HTTP call, which a short cache removes for repeated requests.

Being a valid Supabase user is NOT enough. The account must also have an
active row in `admin_profiles`; otherwise anyone who signed up through any
other route into the same project would be staff.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.errors import AuthError, ForbiddenError
from app.core.logging import get_logger
from app.core.supabase import supabase

logger = get_logger(__name__)

# Short enough that deactivating a staff member takes effect within a minute,
# long enough that a dashboard render is not 20 round trips to the auth API.
CACHE_TTL_SECONDS = 60

_cache: dict[str, tuple[float, AdminIdentity]] = {}


@dataclass(frozen=True)
class AdminIdentity:
    profile_id: str
    auth_user_id: str
    email: str
    full_name: str
    role: str

    @property
    def label(self) -> str:
        return f"{self.full_name} <{self.email}>"

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def _cache_key(token: str) -> str:
    # Never key the cache on the raw token — it would sit in memory in the
    # clear and show up in any dump.
    return hashlib.sha256(token.encode()).hexdigest()


async def sign_in(email: str, password: str) -> dict:
    """Exchange credentials for a session. Raises AuthError on bad details."""
    grant = await supabase.password_grant(email, password)
    access_token = grant.get("access_token")
    if not access_token:
        raise AuthError("Email or password is incorrect.")

    identity = await _resolve(access_token)

    logger.info("admin signed in", extra={"admin_role": identity.role})
    return {
        "access_token": access_token,
        "refresh_token": grant.get("refresh_token"),
        "expires_in": grant.get("expires_in"),
        "admin": {
            "id": identity.profile_id,
            "full_name": identity.full_name,
            "email": identity.email,
            "role": identity.role,
        },
    }


async def _resolve(access_token: str) -> AdminIdentity:
    user = await supabase.user_from_token(access_token)
    if not user or not user.get("id"):
        raise AuthError("Your session has expired. Please sign in again.")

    rows, _ = await supabase.select(
        "admin_profiles",
        columns="id,auth_user_id,full_name,role,active",
        filters={"auth_user_id": f"eq.{user['id']}"},
        limit=1,
    )
    if not rows or not rows[0].get("active"):
        # A real Supabase user with no active staff profile. Logged because it
        # is either a deactivated employee or someone probing the admin API.
        logger.warning("non-admin token presented to the admin API")
        raise ForbiddenError("This account does not have access to the bakery system.")

    profile = rows[0]
    return AdminIdentity(
        profile_id=profile["id"],
        auth_user_id=profile["auth_user_id"],
        email=user.get("email", ""),
        full_name=profile["full_name"],
        role=profile["role"],
    )


async def current_admin(request: Request) -> AdminIdentity:
    """FastAPI dependency. Every admin route depends on this."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError("Please sign in to use the bakery system.")

    token = header[7:].strip()
    if not token:
        raise AuthError("Please sign in to use the bakery system.")

    key = _cache_key(token)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    identity = await _resolve(token)
    _cache[key] = (time.monotonic(), identity)
    return identity


async def require_owner(admin: AdminIdentity = Depends(current_admin)) -> AdminIdentity:
    """For actions only the owner should take — deleting catalog items,
    changing settings that affect pricing."""
    if not admin.is_owner:
        raise ForbiddenError("Only the bakery owner can do that.")
    return admin


def sign_out(token: str) -> None:
    """Drop the cached identity so a signed-out token stops working here
    immediately rather than lingering for the cache TTL."""
    _cache.pop(_cache_key(token), None)
