"""Orchestrates one turn of the design conversation.

The order of operations here is the whole product:

    customer message
      → sanitize                 (injection detection, length cap)
      → language model           proposes an understanding, in NAMES
      → resolver                 maps names onto real catalog rows, or asks again
      → pricing engine           computes the price
      → feasibility engine       decides what needs a human
      → persist                  message, extraction, specification
      → reply                    text + spec + price + what is still missing

The model contributes exactly one thing: the reply text and a guess at what the
customer meant. Everything with a consequence is computed afterwards by code.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.catalog import load_catalog, load_settings, setting_int
from app.schemas.catalog import Catalog
from app.schemas.specification import CakeSpecification
from app.services.ai import prompts, resolver, sessions
from app.services.ai.factory import get_llm_provider
from app.services.ai.providers import ChatMessage
from app.services.ai.safety import sanitize_customer_text
from app.services.availability.rules import compute_lead_time
from app.services.feasibility.engine import check_catalog_consistency, check_feasibility
from app.services.pricing.engine import calculate_price

# check_catalog_consistency is re-exported: the API layer treats this module
# as the single entry point for conversation concerns.
__all__ = [
    "TurnResult", "check_catalog_consistency", "evaluate", "handle_turn",
    "opening_turn", "row_to_spec", "spec_to_row", "specification_display",
]

logger = get_logger(__name__)


class TurnResult(BaseModel):
    reply: str
    suggested_replies: list[str] = Field(default_factory=list)
    specification: dict = Field(default_factory=dict)
    specification_display: dict = Field(default_factory=dict)
    price: dict | None = None
    feasibility: dict | None = None
    missing_information: list[str] = Field(default_factory=list)
    is_complete: bool = False
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"


def specification_display(spec: CakeSpecification, catalog: Catalog) -> dict:
    """The live summary panel. Unknown fields are present and null rather than
    absent, so the UI can show "Not chosen yet" instead of hiding the row."""

    def name_of(getter, item_id):
        item = getter(item_id)
        return item.name if item else None

    return {
        "event_type": spec.event_type,
        "event_date": spec.event_date.isoformat() if spec.event_date else None,
        "servings": spec.servings,
        "size": name_of(catalog.size, spec.size_id),
        "shape": spec.shape,
        "tiers": spec.number_of_tiers,
        "cake_flavor": name_of(catalog.flavor, spec.cake_flavor_id),
        "filling": name_of(catalog.filling, spec.filling_id),
        "frosting": name_of(catalog.frosting, spec.frosting_id),
        "design_style": name_of(catalog.style, spec.design_style_id),
        "colors": spec.colors,
        "decorations": [d.name for d in catalog.decoration_list(spec.decoration_ids)],
        "inscription": spec.inscription,
        "dietary_requirements": [d.name for d in catalog.dietary_list(spec.dietary_requirement_ids)],
        "allergen_notes": spec.allergen_notes,
        "fulfillment_method": spec.fulfillment_method,
        "delivery_address": spec.delivery_address,
    }


def spec_to_row(spec: CakeSpecification, price=None, feasibility=None) -> dict:
    """Database payload for `cake_specifications`."""
    row: dict = {
        "event_type": spec.event_type,
        "event_date": spec.event_date.isoformat() if spec.event_date else None,
        "servings": spec.servings,
        "size_id": str(spec.size_id) if spec.size_id else None,
        "shape": spec.shape,
        "number_of_tiers": spec.number_of_tiers,
        "cake_flavor_id": str(spec.cake_flavor_id) if spec.cake_flavor_id else None,
        "filling_id": str(spec.filling_id) if spec.filling_id else None,
        "frosting_id": str(spec.frosting_id) if spec.frosting_id else None,
        "design_style_id": str(spec.design_style_id) if spec.design_style_id else None,
        "colors": spec.colors,
        "decoration_ids": [str(d) for d in spec.decoration_ids],
        "inscription": spec.inscription,
        "dietary_requirement_ids": [str(d) for d in spec.dietary_requirement_ids],
        "allergen_notes": spec.allergen_notes,
        "customer_budget_cents": spec.customer_budget_cents,
        "fulfillment_method": spec.fulfillment_method,
        "delivery_address": spec.delivery_address,
        "missing_information": spec.missing_information(),
    }
    if price is not None:
        row.update(
            {
                "estimated_price_cents": price.total_cents,
                "price_breakdown": price.model_dump(mode="json"),
                "complexity_level": price.complexity_level,
                "production_points": price.production_points,
            }
        )
    if feasibility is not None:
        row.update(
            {
                "requires_manual_approval": feasibility.outcome != "allow",
                "manual_approval_reasons": feasibility.manual_approval_reasons,
            }
        )
    return row


def row_to_spec(row: dict | None) -> CakeSpecification:
    if not row:
        return CakeSpecification()
    return CakeSpecification(
        event_type=row.get("event_type"),
        event_date=row.get("event_date"),
        servings=row.get("servings"),
        size_id=row.get("size_id"),
        shape=row.get("shape"),
        number_of_tiers=row.get("number_of_tiers"),
        cake_flavor_id=row.get("cake_flavor_id"),
        filling_id=row.get("filling_id"),
        frosting_id=row.get("frosting_id"),
        design_style_id=row.get("design_style_id"),
        colors=row.get("colors") or [],
        decoration_ids=row.get("decoration_ids") or [],
        inscription=row.get("inscription"),
        dietary_requirement_ids=row.get("dietary_requirement_ids") or [],
        allergen_notes=row.get("allergen_notes") or [],
        customer_budget_cents=row.get("customer_budget_cents"),
        fulfillment_method=row.get("fulfillment_method"),
        delivery_address=row.get("delivery_address"),
    )


async def evaluate(spec: CakeSpecification, catalog: Catalog, settings_rows: dict):
    """Price and feasibility for the specification as it stands.

    Runs on every turn so the customer watches the price move as the cake takes
    shape, rather than meeting it at the end.
    """
    lead_hours = None
    if spec.event_date:
        lead = compute_lead_time(
            spec.event_date,
            now=datetime.now(ZoneInfo(get_settings().default_timezone)),
            standard_hours=setting_int(settings_rows, "default_lead_time_hours", 48),
            minimum_hours=setting_int(settings_rows, "min_lead_time_hours", 24),
        )
        lead_hours = lead.hours

    price = calculate_price(
        spec,
        catalog,
        lead_time_hours=lead_hours,
        currency=str(settings_rows.get("currency", "USD")),
    )
    feasibility = check_feasibility(
        spec,
        catalog,
        lead_time_hours=lead_hours,
        total_price_cents=price.total_cents,
        complexity_level=price.complexity_level,
    )
    price.is_estimate = price.is_estimate or feasibility.outcome != "allow"
    return price, feasibility


async def handle_turn(session: dict, customer_message: str) -> TurnResult:
    """One exchange: customer says something, the assistant answers."""
    catalog = await load_catalog()
    settings_rows = await load_settings()

    cleaned, injection_findings = sanitize_customer_text(customer_message)

    current_spec = row_to_spec(await sessions.get_specification_row(session["id"]))

    history = [
        ChatMessage(role=row["role"], content=row["message"])
        for row in await sessions.load_messages(session["id"])
        if row["role"] in ("user", "assistant")
    ]
    history.append(ChatMessage(role="user", content=cleaned))

    await sessions.append_message(
        session["id"],
        role="user",
        message=cleaned,
        structured_data={"injection_patterns": len(injection_findings)} if injection_findings else None,
    )

    provider = get_llm_provider()
    turn = await provider.converse(
        messages=history,
        catalog_summary=prompts.catalog_summary(catalog),
        specification_state=prompts.specification_state(current_spec, catalog),
        missing=current_spec.missing_labels(),
    )

    # The model proposed names; only rows that exist survive this.
    resolution = resolver.resolve(turn.extracted, catalog, current=current_spec)
    spec = resolution.specification
    spec.free_text = f"{current_spec.free_text} {cleaned}".strip()[-4000:]

    price, feasibility = await evaluate(spec, catalog, settings_rows)

    reply = turn.reply
    correction = resolver.unresolved_message(resolution.unresolved, catalog)
    if correction:
        # The model may have cheerfully agreed to something that does not
        # exist. The correction is appended by code, not left to the model.
        reply = f"{correction} {reply}".strip()

    notes = list(resolution.notes)
    for problem in check_catalog_consistency(spec, catalog):
        notes.append(problem)

    await sessions.save_specification(session["id"], spec_to_row(spec, price, feasibility))
    await sessions.append_message(
        session["id"],
        role="assistant",
        message=reply,
        structured_data=turn.extracted.model_dump(mode="json", exclude_defaults=True) or None,
        provider=turn.provider,
        provider_message_id=turn.provider_message_id,
        usage=turn.usage,
    )
    await sessions.touch(
        session["id"], message_count=int(session.get("message_count", 0)) + 2
    )

    missing = spec.missing_labels()
    return TurnResult(
        reply=reply,
        suggested_replies=turn.suggested_replies,
        specification=spec.model_dump(mode="json"),
        specification_display=specification_display(spec, catalog),
        price=price.model_dump(mode="json"),
        feasibility=feasibility.model_dump(mode="json"),
        missing_information=missing,
        is_complete=not missing,
        notes=notes,
        provider=turn.provider,
    )


async def opening_turn(session: dict) -> TurnResult:
    """The assistant speaks first, with an open question (spec section 9)."""
    catalog = await load_catalog()
    reply = "Tell me about the cake you would like to create."

    await sessions.append_message(session["id"], role="assistant", message=reply, provider="system")

    spec = CakeSpecification()
    return TurnResult(
        reply=reply,
        suggested_replies=[
            "It is for a birthday",
            "It is for a wedding",
            "I need it for a company event",
        ],
        specification=spec.model_dump(mode="json"),
        specification_display=specification_display(spec, catalog),
        missing_information=spec.missing_labels(),
        is_complete=False,
    )
