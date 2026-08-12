"""The structured cake specification — the operational source of truth.

The generated image represents this object, never the other way round
(spec section 20). Catalog choices are IDs: the language model resolves a name
to a row before it gets here, so an option the bakery does not make cannot
enter the system.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

CakeShape = Literal["round", "square", "rectangle", "heart", "custom"]
FulfillmentMethod = Literal["pickup", "delivery"]

# Everything an order needs before it can be priced and produced. Anything
# missing from here is what the assistant still has to ask about.
REQUIRED_FIELDS: tuple[str, ...] = (
    "event_type",
    "event_date",
    "servings",
    "size_id",
    "cake_flavor_id",
    "filling_id",
    "frosting_id",
    "design_style_id",
    "fulfillment_method",
)

FIELD_LABELS: dict[str, str] = {
    "event_type": "the occasion",
    "event_date": "the date you need it",
    "servings": "how many people it should serve",
    "size_id": "the cake size",
    "cake_flavor_id": "the cake flavour",
    "filling_id": "the filling",
    "frosting_id": "the finish",
    "design_style_id": "the design style",
    "fulfillment_method": "collection or delivery",
    "delivery_address": "the delivery address",
}


class CakeSpecification(BaseModel):
    """A specification in progress. Every field is optional while the
    conversation is still running; `missing_information()` reports what is
    still needed rather than raising."""

    event_type: str | None = None
    event_date: date | None = None
    servings: int | None = Field(default=None, gt=0, le=500)

    size_id: UUID | None = None
    shape: CakeShape | None = None
    number_of_tiers: int | None = Field(default=None, ge=1, le=5)

    cake_flavor_id: UUID | None = None
    filling_id: UUID | None = None
    frosting_id: UUID | None = None
    design_style_id: UUID | None = None

    colors: list[str] = Field(default_factory=list, max_length=6)
    decoration_ids: list[UUID] = Field(default_factory=list, max_length=12)
    inscription: str | None = Field(default=None, max_length=120)

    dietary_requirement_ids: list[UUID] = Field(default_factory=list)
    allergen_notes: list[str] = Field(default_factory=list)

    fulfillment_method: FulfillmentMethod | None = None
    delivery_address: str | None = None
    delivery_latitude: float | None = None
    delivery_longitude: float | None = None

    customer_budget_cents: int | None = Field(default=None, ge=0)

    # Free text the customer has written. Kept so the feasibility engine can
    # match phrases like "suspended" or "allergen free guarantee" that never
    # become structured fields.
    free_text: str = ""

    @field_validator("inscription")
    @classmethod
    def _clean_inscription(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("colors")
    @classmethod
    def _clean_colors(cls, values: list[str]) -> list[str]:
        return [v.strip().lower() for v in values if v and v.strip()]

    def missing_information(self) -> list[str]:
        """Required fields that are still unknown.

        Delivery orders additionally need an address; pickup orders do not,
        so the requirement is conditional rather than a fixed list.
        """
        missing = [name for name in REQUIRED_FIELDS if getattr(self, name) in (None, [], "")]
        if self.fulfillment_method == "delivery" and not self.delivery_address:
            missing.append("delivery_address")
        return missing

    def is_complete(self) -> bool:
        return not self.missing_information()

    def missing_labels(self) -> list[str]:
        """Human phrasing for the assistant to ask about."""
        return [FIELD_LABELS.get(name, name) for name in self.missing_information()]
