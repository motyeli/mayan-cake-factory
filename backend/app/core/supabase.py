"""Async Supabase access: PostgREST, RPC, Storage and Auth.

WHY NOT supabase-py: its client is synchronous, so every call would block
FastAPI's event loop. This is a thin async wrapper over the same REST
endpoints — one shared httpx.AsyncClient, connection pooled, no blocking.

The service-role key used here bypasses RLS. It exists only in this process,
is never sent to a browser, and is redacted from logs by the formatter.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Errors raised by create_order_atomic / reserve_production_capacity that mean
# "someone else took the slot", not "the server is broken".
_CAPACITY_ERRORS = {
    "DATE_BLOCKED": "That date is not available for orders.",
    "DATE_FULL": "That date is fully booked.",
    "TIME_SLOT_FULL": "That time window is fully booked.",
    "TIME_SLOT_UNAVAILABLE": "That time window is not available.",
    "INVALID_INITIAL_STATUS": "The order could not be opened in that state.",
}


class SupabaseClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base = settings.supabase_url.rstrip("/")
        self._service_key = settings.supabase_service_role_key
        self._anon_key = settings.supabase_anon_key
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("SupabaseClient.start() was not called")
        return self._client

    @property
    def configured(self) -> bool:
        return bool(self._base and self._service_key)

    # --------------------------------------------------------------- helpers

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
        }
        headers.update(extra or {})
        return headers

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("supabase request failed", extra={"error_type": type(exc).__name__})
            raise ProviderError("The database is temporarily unreachable.") from exc

        if response.status_code >= 400:
            self._raise_for(response)
        return response

    def _raise_for(self, response: httpx.Response) -> None:
        message = ""
        try:
            message = response.json().get("message", "")
        except Exception:
            message = response.text[:200]

        # Map the plpgsql capacity errors onto 409 so the customer sees a
        # useful message instead of a 500.
        for token, friendly in _CAPACITY_ERRORS.items():
            if token in message:
                raise ConflictError(friendly, {"reason": token})

        logger.error(
            "supabase error response",
            extra={"status": response.status_code, "error_type": "supabase"},
        )
        raise ProviderError("The database rejected that request.")

    # ------------------------------------------------------------- postgrest

    async def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        count: bool = False,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Returns (rows, total). `total` is None unless count=True."""
        params: dict[str, Any] = {"select": columns, **(filters or {})}
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        headers = self._headers({"Prefer": "count=exact"} if count else None)
        response = await self._send("GET", f"{self._base}/rest/v1/{table}", params=params, headers=headers)

        total = None
        if count:
            content_range = response.headers.get("Content-Range", "*/0")
            tail = content_range.split("/")[-1]
            total = int(tail) if tail.isdigit() else None
        return response.json(), total

    async def select_one(
        self, table: str, *, columns: str = "*", filters: dict[str, str], missing: str = "Not found."
    ) -> dict[str, Any]:
        rows, _ = await self.select(table, columns=columns, filters=filters, limit=1)
        if not rows:
            raise NotFoundError(missing)
        return rows[0]

    async def insert(
        self, table: str, payload: dict[str, Any] | list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        response = await self._send(
            "POST",
            f"{self._base}/rest/v1/{table}",
            json=payload,
            headers=self._headers({"Prefer": "return=representation"}),
        )
        return response.json()

    async def update(
        self, table: str, *, filters: dict[str, str], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        response = await self._send(
            "PATCH",
            f"{self._base}/rest/v1/{table}",
            params=filters,
            json=payload,
            headers=self._headers({"Prefer": "return=representation"}),
        )
        return response.json()

    async def delete(self, table: str, *, filters: dict[str, str]) -> None:
        await self._send(
            "DELETE", f"{self._base}/rest/v1/{table}", params=filters, headers=self._headers()
        )

    async def rpc(self, function: str, payload: dict[str, Any] | None = None) -> Any:
        response = await self._send(
            "POST",
            f"{self._base}/rest/v1/rpc/{function}",
            json=payload or {},
            headers=self._headers(),
        )
        return response.json() if response.content else None

    # ----------------------------------------------------------------- storage

    async def upload(
        self, bucket: str, path: str, data: bytes, content_type: str, upsert: bool = False
    ) -> str:
        await self._send(
            "POST" if not upsert else "PUT",
            f"{self._base}/storage/v1/object/{bucket}/{path}",
            content=data,
            headers={
                "apikey": self._service_key,
                "Authorization": f"Bearer {self._service_key}",
                "Content-Type": content_type,
            },
        )
        return f"{bucket}/{path}"

    async def signed_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Time-limited URL for a private object. Never logged in full."""
        response = await self._send(
            "POST",
            f"{self._base}/storage/v1/object/sign/{bucket}/{path}",
            json={"expiresIn": expires_in},
            headers=self._headers(),
        )
        return f"{self._base}/storage/v1{response.json()['signedURL']}"

    # -------------------------------------------------------------------- auth

    async def password_grant(self, email: str, password: str) -> dict[str, Any]:
        """Exchange admin credentials for a Supabase JWT.

        Done server-side so the browser never holds the anon key or talks to
        the auth service directly.
        """
        response = await self.client.post(
            f"{self._base}/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            headers={"apikey": self._anon_key, "Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            from app.core.errors import AuthError

            raise AuthError("Email or password is incorrect.")
        return response.json()

    async def user_from_token(self, access_token: str) -> dict[str, Any] | None:
        """Verify an admin JWT by asking Supabase who it belongs to.

        Chosen over local signature checking because it works whether the
        project signs with a shared secret or asymmetric keys, and needs no
        key rotation handling. Callers cache the result briefly.
        """
        try:
            response = await self.client.get(
                f"{self._base}/auth/v1/user",
                headers={"apikey": self._anon_key, "Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError:
            return None
        return response.json() if response.status_code == 200 else None

    # ------------------------------------------------------------------ health

    async def ping(self) -> Literal["ok", "unconfigured", "unreachable"]:
        """Never raises. A health endpoint that can 500 is worse than useless,
        because the orchestrator cannot distinguish "app is down" from
        "dependency check is broken"."""
        if not self.configured or self._client is None:
            return "unconfigured"
        try:
            response = await self.client.get(
                f"{self._base}/rest/v1/settings",
                params={"select": "key", "limit": 1},
                headers=self._headers(),
            )
            return "ok" if response.status_code < 400 else "unreachable"
        except httpx.HTTPError:
            return "unreachable"


supabase = SupabaseClient()
