"""Application settings.

Read once at startup from the environment (or backend/.env locally). Values
that Mayan can change at runtime — prices, capacity, lead times — do NOT
belong here; they live in the `settings` table so a change does not need a
deployment. What lives here is infrastructure: credentials, URLs, modes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application ---------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "Mayan's Cake Factory"
    secret_key: str = "dev-only-not-a-real-secret"  # noqa: S105 - placeholder; real value from env
    log_level: str = "INFO"

    frontend_url: str = "http://localhost:8000"
    backend_url: str = "http://localhost:8001"
    allowed_origins: str = "http://localhost:8000"

    # --- supabase --------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # --- ai ---------------------------------------------------------------
    ai_mode: Literal["mock", "live"] = "mock"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    image_provider: str = "openai"
    image_api_key: str = ""
    image_model: str = "gpt-image-1"

    # --- maps -------------------------------------------------------------
    maps_provider: str = "mock"
    maps_api_key: str = ""

    # --- bakery ------------------------------------------------------------
    bakery_name: str = "Mayan's Cake Factory"
    bakery_address: str = ""
    bakery_latitude: float = 48.8584
    bakery_longitude: float = 2.2945

    # --- business defaults (the settings table overrides these) -----------
    default_currency: str = "USD"
    default_timezone: str = "Europe/Paris"
    design_link_expiration_days: int = 14
    max_design_revisions: int = 3

    # --- abuse protection ---------------------------------------------------
    rate_limit_messages_per_minute: int = 20
    rate_limit_generations_per_hour: int = 10
    max_upload_bytes: int = 5 * 1024 * 1024

    @field_validator("allowed_origins")
    @classmethod
    def _no_wildcard_in_production(cls, value: str, info) -> str:
        # A wildcard origin plus credentials is the classic CORS mistake.
        if info.data.get("app_env") == "production" and "*" in value:
            raise ValueError("ALLOWED_ORIGINS must not contain '*' in production")
        return value

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def ai_is_mocked(self) -> bool:
        return self.ai_mode == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience for modules that only need a couple of fields.
settings: Settings = get_settings()


def missing_credentials() -> list[str]:
    """Names of credentials the current configuration needs but does not have.

    Used by the health endpoint so a misconfigured deployment reports itself
    instead of failing on the first customer request.
    """
    s = get_settings()
    missing: list[str] = []
    for name in ("supabase_url", "supabase_service_role_key", "supabase_anon_key"):
        if not getattr(s, name):
            missing.append(name.upper())
    if s.ai_mode == "live":
        for name in ("llm_api_key", "image_api_key"):
            if not getattr(s, name):
                missing.append(name.upper())
    if s.maps_provider != "mock" and not s.maps_api_key:
        missing.append("MAPS_API_KEY")
    return missing
