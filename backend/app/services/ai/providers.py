"""AI provider interfaces.

Spec section 10 asks for separate abstractions for conversation, structured
extraction, image generation and image revision. They are declared separately
here so the boundaries are explicit; a single concrete class may implement more
than one, because for modern models conversation and extraction are one API
call and splitting them would double the cost and let the two drift apart.

Nothing outside this package knows which vendor is in use. Selection happens in
`factory.py` from environment variables, and `AI_MODE=mock` needs no
credentials at all.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ExtractedSpecification(BaseModel):
    """What the model believes the customer has asked for.

    Deliberately NAMES, not IDs. The model never sees or invents an identifier;
    `resolver.py` maps these strings onto real catalog rows and rejects
    anything that does not match. A hallucinated flavour dies here rather than
    reaching the price.
    """

    event_type: str | None = None
    event_date: str | None = None
    servings: int | None = None
    size: str | None = None
    shape: str | None = None
    tiers: int | None = None
    cake_flavor: str | None = None
    filling: str | None = None
    frosting: str | None = None
    design_style: str | None = None
    colors: list[str] = Field(default_factory=list)
    decorations: list[str] = Field(default_factory=list)
    inscription: str | None = None
    dietary_requirements: list[str] = Field(default_factory=list)
    allergen_notes: list[str] = Field(default_factory=list)
    fulfillment_method: str | None = None
    delivery_address: str | None = None
    customer_budget: float | None = None


class AssistantTurn(BaseModel):
    """One reply from the assistant plus what it understood."""

    reply: str
    extracted: ExtractedSpecification = Field(default_factory=ExtractedSpecification)
    suggested_replies: list[str] = Field(default_factory=list)
    provider: str = "mock"
    provider_message_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(Protocol):
    """Conversational language model."""

    name: str

    async def converse(
        self,
        *,
        messages: list[ChatMessage],
        catalog_summary: str,
        specification_state: str,
        missing: list[str],
    ) -> AssistantTurn: ...


class ExtractionProvider(Protocol):
    """Structured extraction from a conversation.

    Separate interface per spec section 10. Implementations may satisfy this
    and `LLMProvider` with the same call.
    """

    name: str

    async def extract(
        self, *, messages: list[ChatMessage], current: ExtractedSpecification
    ) -> ExtractedSpecification: ...


class GeneratedImage(BaseModel):
    data: bytes
    content_type: str = "image/png"
    prompt: str = ""
    provider: str = "mock"
    provider_result_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


class ImageGenerationProvider(Protocol):
    name: str

    async def generate(self, *, prompt: str) -> GeneratedImage: ...


class ImageRevisionProvider(Protocol):
    name: str

    async def revise(
        self, *, prompt: str, instruction: str, previous_image: bytes | None = None
    ) -> GeneratedImage: ...
