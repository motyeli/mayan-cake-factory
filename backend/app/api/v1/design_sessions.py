"""Guest design-session endpoints.

The token in the path IS the credential — there are no accounts. Every handler
resolves it through `sessions.get_session`, which rejects unknown and expired
tokens, so no route can be reached without a valid one.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.repositories.catalog import load_catalog, load_settings, setting_int
from app.services.ai import conversation, sessions
from app.services.ai.conversation import row_to_spec, spec_to_row

router = APIRouter(prefix="/design-sessions", tags=["design sessions"])


def _client_hash(request: Request) -> str:
    """Coarse identifier for rate limiting and abuse detection.

    Hashed, and never stored or logged in the clear — an IP address is personal
    data under GDPR and the bakery has no reason to hold one.
    """
    client = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{client}:{get_settings().secret_key}".encode()).hexdigest()[:32]


class CreateSessionResponse(BaseModel):
    token: str
    expires_at: str
    turn: dict


@router.post("", summary="Start a design session")
async def create_session(request: Request) -> CreateSessionResponse:
    limiter.hit(f"session-create:{_client_hash(request)}", limit=10, per_seconds=3600)

    settings_rows = await load_settings()
    token, session = await sessions.create_session(
        expires_days=setting_int(settings_rows, "design_link_expiration_days", 14),
        ip_hash=_client_hash(request),
    )
    turn = await conversation.opening_turn(session)

    # The token is returned here and never again — only its hash is stored.
    return CreateSessionResponse(
        token=token, expires_at=session["expires_at"], turn=turn.model_dump(mode="json")
    )


@router.get("/{token}", summary="Resume a saved design")
async def get_session(token: str) -> dict:
    session = await sessions.get_session(token)
    catalog = await load_catalog()
    settings_rows = await load_settings()

    spec = row_to_spec(await sessions.get_specification_row(session["id"]))
    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)

    return {
        "status": session["status"],
        "expires_at": session["expires_at"],
        "revision_count": session["revision_count"],
        "messages": await sessions.load_messages(session["id"]),
        "specification": spec.model_dump(mode="json"),
        "specification_display": conversation.specification_display(spec, catalog),
        "price": price.model_dump(mode="json"),
        "feasibility": feasibility.model_dump(mode="json"),
        "missing_information": spec.missing_labels(),
        "is_complete": spec.is_complete(),
    }


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.post("/{token}/messages", summary="Send a message to the assistant")
async def send_message(token: str, body: MessageRequest, request: Request) -> dict:
    session = await sessions.get_session(token)

    # Per session, not per IP: a shared office network must not lock out one
    # customer because a colleague is also ordering a cake.
    limiter.hit(
        f"messages:{session['id']}",
        limit=get_settings().rate_limit_messages_per_minute,
        per_seconds=60,
    )

    turn = await conversation.handle_turn(session, body.message)
    return turn.model_dump(mode="json")


@router.get("/{token}/specification", summary="Current structured specification")
async def get_specification(token: str) -> dict:
    session = await sessions.get_session(token)
    catalog = await load_catalog()
    settings_rows = await load_settings()

    spec = row_to_spec(await sessions.get_specification_row(session["id"]))
    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)

    return {
        "specification": spec.model_dump(mode="json"),
        "specification_display": conversation.specification_display(spec, catalog),
        "price": price.model_dump(mode="json"),
        "feasibility": feasibility.model_dump(mode="json"),
        "missing_information": spec.missing_labels(),
        "is_complete": spec.is_complete(),
    }


class SpecificationPatch(BaseModel):
    """Direct edits from the summary screen's "Change" links.

    Catalog fields are IDs here, not names: this comes from the UI, which
    already knows the identifiers, so no resolution step is needed.
    """

    event_type: str | None = None
    event_date: str | None = None
    servings: int | None = Field(default=None, gt=0, le=500)
    size_id: str | None = None
    shape: str | None = None
    number_of_tiers: int | None = Field(default=None, ge=1, le=5)
    cake_flavor_id: str | None = None
    filling_id: str | None = None
    frosting_id: str | None = None
    design_style_id: str | None = None
    colors: list[str] | None = None
    decoration_ids: list[str] | None = None
    inscription: str | None = Field(default=None, max_length=120)
    dietary_requirement_ids: list[str] | None = None
    fulfillment_method: str | None = None
    delivery_address: str | None = None


@router.patch("/{token}/specification", summary="Edit the specification directly")
async def patch_specification(token: str, body: SpecificationPatch) -> dict:
    session = await sessions.get_session(token)
    catalog = await load_catalog()
    settings_rows = await load_settings()

    spec = row_to_spec(await sessions.get_specification_row(session["id"]))

    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(spec, field, value)

    # Re-validate through the model so an ID that is not a real catalog row,
    # or a shape that does not exist, is rejected here rather than at ordering.
    spec = spec.model_validate(spec.model_dump())

    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)
    await sessions.save_specification(session["id"], spec_to_row(spec, price, feasibility))

    return {
        "specification": spec.model_dump(mode="json"),
        "specification_display": conversation.specification_display(spec, catalog),
        "price": price.model_dump(mode="json"),
        "feasibility": feasibility.model_dump(mode="json"),
        "missing_information": spec.missing_labels(),
        "is_complete": spec.is_complete(),
    }


@router.post("/{token}/validate", summary="Confirm the specification before design")
async def validate_specification(token: str) -> dict:
    """The gate before image generation (spec section 8.3).

    Confirmation is refused while anything is missing or infeasible, so an
    image is never generated for a cake that cannot be produced.
    """
    session = await sessions.get_session(token)
    catalog = await load_catalog()
    settings_rows = await load_settings()

    spec = row_to_spec(await sessions.get_specification_row(session["id"]))
    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)
    problems = conversation.check_catalog_consistency(spec, catalog)
    missing = spec.missing_labels()

    can_confirm = not missing and not problems and feasibility.outcome != "reject"

    if can_confirm:
        await sessions.save_specification(
            session["id"], {**spec_to_row(spec, price, feasibility), "confirmed_by_customer": True}
        )
        await sessions.touch(session["id"], status="specification_confirmed")

    return {
        "can_confirm": can_confirm,
        "confirmed": can_confirm,
        "missing_information": missing,
        "consistency_problems": problems,
        "specification_display": conversation.specification_display(spec, catalog),
        "price": price.model_dump(mode="json"),
        "feasibility": feasibility.model_dump(mode="json"),
        "disclaimers": {
            "allergen": settings_rows.get("allergen_disclaimer"),
            "image": settings_rows.get("visual_disclaimer"),
            "inspiration": settings_rows.get("inspiration_disclaimer"),
        },
    }
