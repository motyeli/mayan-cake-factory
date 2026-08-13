"""OpenAI adapter.

Uses JSON-schema structured output so the extraction arrives as validated
fields rather than prose to be parsed. One call returns both the customer-facing
reply and the structured update; splitting them would double the cost and let
the two disagree about the same message.

Only activated when AI_MODE=live. Failures raise ProviderError and the caller
falls back to the mock, so a provider outage degrades the conversation instead
of breaking the order flow.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.services.ai.prompts import SYSTEM_PROMPT
from app.services.ai.providers import (
    AssistantTurn,
    ChatMessage,
    ExtractedSpecification,
    GeneratedImage,
)
from app.services.ai.safety import wrap_customer_text

logger = get_logger(__name__)

API_BASE = "https://api.openai.com/v1"

# Mirrors ExtractedSpecification. Everything is optional and nullable: the model
# must be able to say "this message told me nothing new" without inventing a
# value to satisfy the schema.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "extracted", "suggested_replies"],
    "properties": {
        "reply": {"type": "string", "description": "What to say to the customer."},
        "suggested_replies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to three short quick-reply options.",
        },
        "extracted": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "event_type", "event_date", "servings", "size", "shape", "tiers",
                "cake_flavor", "filling", "frosting", "design_style", "colors",
                "decorations", "inscription", "dietary_requirements",
                "allergen_notes", "fulfillment_method", "delivery_address",
                "customer_budget",
            ],
            "properties": {
                "event_type": {"type": ["string", "null"]},
                "event_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "servings": {"type": ["integer", "null"]},
                "size": {"type": ["string", "null"], "description": "Exact catalog name"},
                "shape": {"type": ["string", "null"]},
                "tiers": {"type": ["integer", "null"]},
                "cake_flavor": {"type": ["string", "null"]},
                "filling": {"type": ["string", "null"]},
                "frosting": {"type": ["string", "null"]},
                "design_style": {"type": ["string", "null"]},
                "colors": {"type": "array", "items": {"type": "string"}},
                "decorations": {"type": "array", "items": {"type": "string"}},
                "inscription": {"type": ["string", "null"]},
                "dietary_requirements": {"type": "array", "items": {"type": "string"}},
                "allergen_notes": {"type": "array", "items": {"type": "string"}},
                "fulfillment_method": {
                    "type": ["string", "null"], "enum": ["pickup", "delivery", None]
                },
                "delivery_address": {"type": ["string", "null"]},
                "customer_budget": {"type": ["number", "null"]},
            },
        },
    },
}


class OpenAILLM:
    """Implements LLMProvider and ExtractionProvider."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def converse(
        self,
        *,
        messages: list[ChatMessage],
        catalog_summary: str,
        specification_state: str,
        missing: list[str],
    ) -> AssistantTurn:
        # The catalog and current state go in the SYSTEM role; only customer
        # words go in the user role, and each is wrapped as data.
        system = (
            f"{SYSTEM_PROMPT}\n\n"
            f"CATALOG — offer nothing outside this:\n{catalog_summary}\n\n"
            f"ALREADY KNOWN — do not ask again:\n{specification_state}\n\n"
            f"STILL NEEDED: {', '.join(missing) if missing else 'nothing'}"
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                *[
                    {
                        "role": m.role,
                        "content": wrap_customer_text(m.content) if m.role == "user" else m.content,
                    }
                    for m in messages
                ],
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "cake_design_turn",
                    "strict": True,
                    "schema": _RESPONSE_SCHEMA,
                },
            },
            "temperature": 0.4,
        }

        data = await self._post("/chat/completions", payload)

        import json

        try:
            choice = data["choices"][0]
            content = json.loads(choice["message"]["content"])
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("openai returned an unusable response", extra={"error_type": type(exc).__name__})
            raise ProviderError("The design assistant is unavailable right now.") from exc

        usage = data.get("usage", {})
        return AssistantTurn(
            reply=content.get("reply", ""),
            extracted=ExtractedSpecification(
                **{k: v for k, v in (content.get("extracted") or {}).items() if v is not None}
            ),
            suggested_replies=(content.get("suggested_replies") or [])[:3],
            provider=self.name,
            provider_message_id=data.get("id"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "model": self._model,
            },
        )

    async def extract(
        self, *, messages: list[ChatMessage], current: ExtractedSpecification
    ) -> ExtractedSpecification:
        turn = await self.converse(
            messages=messages, catalog_summary="", specification_state="", missing=[]
        )
        return turn.extracted

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(
                    f"{API_BASE}{path}",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            logger.error("openai request failed", extra={"error_type": type(exc).__name__})
            raise ProviderError("The design assistant is unavailable right now.") from exc

        if response.status_code >= 400:
            # Status only — the body can echo the prompt, which is customer data.
            logger.error("openai error response", extra={"status": response.status_code})
            raise ProviderError("The design assistant is unavailable right now.")
        return response.json()


class OpenAIImages:
    """Implements ImageGenerationProvider and ImageRevisionProvider."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def generate(self, *, prompt: str) -> GeneratedImage:
        return await self._create(prompt)

    async def revise(
        self, *, prompt: str, instruction: str, previous_image: bytes | None = None
    ) -> GeneratedImage:
        # The full prompt is rebuilt from the revised specification, so the
        # revision is expressed as a complete description rather than a diff
        # against an image the model would have to re-interpret.
        return await self._create(f"{prompt}\n\nRevision requested: {instruction}")

    async def _create(self, prompt: str) -> GeneratedImage:
        import base64

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
                response = await client.post(
                    f"{API_BASE}/images/generations",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "size": "1024x1024",
                        "n": 1,
                    },
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            logger.error("openai image request failed", extra={"error_type": type(exc).__name__})
            raise ProviderError("The design could not be generated right now.") from exc

        if response.status_code >= 400:
            logger.error("openai image error", extra={"status": response.status_code})
            raise ProviderError("The design could not be generated right now.")

        data = response.json()
        try:
            first = data["data"][0]
            raw = base64.b64decode(first["b64_json"])
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError("The design could not be generated right now.") from exc

        return GeneratedImage(
            data=raw,
            content_type="image/png",
            prompt=prompt,
            provider=self.name,
            provider_result_id=str(data.get("created", "")),
            usage={"model": self._model},
        )


def build_openai_llm() -> OpenAILLM:
    settings = get_settings()
    if not settings.llm_api_key:
        raise ProviderError("LLM_API_KEY is not configured.")
    return OpenAILLM(settings.llm_api_key, settings.llm_model)


def build_openai_images() -> OpenAIImages:
    settings = get_settings()
    if not settings.image_api_key:
        raise ProviderError("IMAGE_API_KEY is not configured.")
    return OpenAIImages(settings.image_api_key, settings.image_model)
