"""Turns what the model said into what the bakery actually makes.

This is the enforcement point for the project's central rule. The model emits
NAMES; nothing downstream accepts anything but catalog IDs. A flavour the
bakery does not make cannot survive this function, no matter how confidently
the model asserted it.

Matching is deliberately conservative:

  1. exact, case-insensitive
  2. substring, when unambiguous
  3. close spelling match at a high cutoff

Anything else is reported as unresolved so the assistant asks again. Guessing
"Pistachio" from "chocolate" would be worse than another question.
"""

from __future__ import annotations

from datetime import date, datetime
from difflib import get_close_matches

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.schemas.catalog import Catalog
from app.schemas.specification import CakeSpecification
from app.services.ai.providers import ExtractedSpecification

logger = get_logger(__name__)

# High enough that "vanila" matches Vanilla but "vanilla-ish thing" does not
# silently become something else.
_FUZZY_CUTOFF = 0.82

_SHAPES = {"round", "square", "rectangle", "heart", "custom"}
_FULFILLMENT = {
    "pickup": "pickup", "collect": "pickup", "collection": "pickup", "self": "pickup",
    "delivery": "delivery", "deliver": "delivery", "delivered": "delivery",
}


class Resolution(BaseModel):
    """What was understood, and what could not be."""

    specification: CakeSpecification
    unresolved: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def _match(value: str | None, options: list) -> object | None:
    if not value:
        return None
    needle = value.strip().lower()
    if not needle:
        return None

    by_name = {item.name.lower(): item for item in options}

    if needle in by_name:
        return by_name[needle]

    # Unambiguous substring: "raspberry" -> "Raspberry cream", but only when
    # exactly one option contains it.
    contains = [item for name, item in by_name.items() if needle in name or name in needle]
    if len(contains) == 1:
        return contains[0]

    close = get_close_matches(needle, list(by_name), n=1, cutoff=_FUZZY_CUTOFF)
    return by_name[close[0]] if close else None


def _match_many(values: list[str], options: list) -> tuple[list, list[str]]:
    matched, missed = [], []
    for value in values or []:
        item = _match(value, options)
        if item is not None:
            if item.id not in [m.id for m in matched]:
                matched.append(item)
        elif value.strip():
            missed.append(value.strip())
    return matched, missed


def _parse_date(value: str | None, today: date | None = None) -> date | None:
    if not value:
        return None

    today = today or date.today()
    parsed = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%B %d %Y", "%d %b %Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt).date()
            break
        except ValueError:
            continue

    if parsed is None:
        return None
    if parsed >= today:
        return parsed

    # A language model has no clock and dates from its training era: in live
    # testing "12 September" came back as 2024-09-12. A past fulfilment date
    # would fail every lead-time check, so the year is corrected to the next
    # occurrence rather than accepted.
    for years in (1, 2):
        try:
            candidate = parsed.replace(year=parsed.year + years)
        except ValueError:  # 29 February in a non-leap year
            return None
        if candidate >= today:
            return candidate
    return None


def resolve(
    extracted: ExtractedSpecification,
    catalog: Catalog,
    *,
    current: CakeSpecification | None = None,
) -> Resolution:
    """Merge an extraction into the running specification.

    Only fields the model actually reported are touched — a turn about the
    colour scheme must not wipe the flavour chosen three messages ago.
    """
    spec = (current or CakeSpecification()).model_copy(deep=True)
    unresolved: dict[str, str] = {}
    notes: list[str] = []

    if extracted.event_type:
        spec.event_type = extracted.event_type.strip()[:80]

    if extracted.event_date:
        parsed = _parse_date(extracted.event_date)
        if parsed:
            spec.event_date = parsed
        else:
            unresolved["event_date"] = extracted.event_date

    if extracted.servings and 0 < extracted.servings <= 500:
        spec.servings = extracted.servings

    # --- catalog-backed fields -------------------------------------------
    for field, value, options, target in (
        ("size", extracted.size, catalog.sizes, "size_id"),
        ("cake_flavor", extracted.cake_flavor, catalog.flavors, "cake_flavor_id"),
        ("filling", extracted.filling, catalog.fillings, "filling_id"),
        ("frosting", extracted.frosting, catalog.frostings, "frosting_id"),
        ("design_style", extracted.design_style, catalog.styles, "design_style_id"),
    ):
        if not value:
            continue
        item = _match(value, options)
        if item is None:
            unresolved[field] = value
        else:
            setattr(spec, target, item.id)

    # Size not stated but guest count known: recommend rather than leave blank.
    if spec.size_id is None and spec.servings:
        suggested = catalog.size_for_servings(spec.servings)
        if suggested:
            spec.size_id = suggested.id
            notes.append(
                f"Suggested the {suggested.name} size, which serves "
                f"{suggested.min_servings} to {suggested.max_servings}."
            )

    decorations, missed = _match_many(extracted.decorations, catalog.decorations)
    if decorations:
        spec.decoration_ids = [d.id for d in decorations]
    if missed:
        unresolved["decorations"] = ", ".join(missed)

    dietary, missed = _match_many(extracted.dietary_requirements, catalog.dietary_options)
    if dietary:
        spec.dietary_requirement_ids = [d.id for d in dietary]
    if missed:
        unresolved["dietary_requirements"] = ", ".join(missed)

    # --- free-form fields --------------------------------------------------
    if extracted.colors:
        spec.colors = [c.strip().lower() for c in extracted.colors if c and c.strip()][:6]

    if extracted.inscription is not None:
        spec.inscription = extracted.inscription.strip()[:120] or None

    if extracted.allergen_notes:
        spec.allergen_notes = [n.strip() for n in extracted.allergen_notes if n and n.strip()]

    if extracted.shape:
        shape = extracted.shape.strip().lower()
        if shape in _SHAPES:
            spec.shape = shape
        else:
            unresolved["shape"] = extracted.shape

    if extracted.tiers and 1 <= extracted.tiers <= 5:
        spec.number_of_tiers = extracted.tiers

    if extracted.fulfillment_method:
        method = _FULFILLMENT.get(extracted.fulfillment_method.strip().lower())
        if method:
            spec.fulfillment_method = method
        else:
            unresolved["fulfillment_method"] = extracted.fulfillment_method

    if extracted.delivery_address:
        spec.delivery_address = extracted.delivery_address.strip()[:300]

    # Budget is guidance for the assistant's suggestions. It never changes a
    # price — the pricing engine does not read it.
    if extracted.customer_budget and extracted.customer_budget > 0:
        spec.customer_budget_cents = int(round(extracted.customer_budget * 100))

    if unresolved:
        logger.info(
            "catalog values could not be resolved",
            extra={"unresolved_fields": sorted(unresolved)},
        )

    return Resolution(specification=spec, unresolved=unresolved, notes=notes)


def unresolved_message(unresolved: dict[str, str], catalog: Catalog) -> str | None:
    """A customer-facing sentence about what could not be matched.

    Names the real options rather than saying "invalid choice", because the
    customer has no way of knowing what the bakery offers.
    """
    if not unresolved:
        return None

    options = {
        "cake_flavor": ("flavour", [f.name for f in catalog.flavors]),
        "filling": ("filling", [f.name for f in catalog.fillings]),
        "frosting": ("finish", [f.name for f in catalog.frostings]),
        "design_style": ("style", [s.name for s in catalog.styles]),
        "size": ("size", [s.name for s in catalog.sizes]),
    }

    parts = []
    for field, value in unresolved.items():
        if field in options:
            label, available = options[field]
            parts.append(f"We do not have “{value}” as a {label}. We offer: {', '.join(available)}.")
        elif field == "decorations":
            parts.append(f"We could not match these decorations: {value}.")
        elif field == "event_date":
            parts.append(f"I could not read “{value}” as a date — could you give it as a day and month?")
    return " ".join(parts) if parts else None
