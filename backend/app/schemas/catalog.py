"""Catalog rows and the immutable snapshot the engines work against.

The engines are pure functions over `(specification, catalog, settings)`. They
never touch the database, which is what makes the business rules cheap to test
and impossible to accidentally couple to request state.

Money is integer cents throughout. Percentages are basis points (2000 = 20%),
so no float ever touches a price.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    """Fields every catalog table shares (spec section 39)."""

    id: UUID
    name: str
    description: str | None = None
    price_adjustment_cents: int = 0
    production_points: int = 0
    preparation_hours: int = 0
    requires_manual_approval: bool = False
    active: bool = True
    display_order: int = 0


class CakeSize(CatalogItem):
    min_servings: int
    max_servings: int
    base_price_cents: int
    tiers: int = 1
    production_points: int = 1

    def fits(self, servings: int) -> bool:
        return self.min_servings <= servings <= self.max_servings


class CakeFlavor(CatalogItem):
    is_premium: bool = False


class Filling(CatalogItem):
    is_premium: bool = False


class Frosting(CatalogItem):
    pickup_only: bool = False
    # None means no transport restriction.
    max_delivery_km: float | None = None


class DesignStyle(CatalogItem):
    base_complexity_level: int = 1
    image_prompt_hint: str | None = None


class Decoration(CatalogItem):
    max_price_cents: int | None = None
    complexity_points: int = 0
    food_safe: bool = True
    requires_barrier: bool = False


class DietaryOption(CatalogItem):
    severe_allergy_flag: bool = False


class DeliveryZone(BaseModel):
    id: UUID
    name: str
    min_distance_km: float
    max_distance_km: float
    delivery_fee_cents: int
    requires_manual_approval: bool = False
    active: bool = True
    display_order: int = 0

    def covers(self, distance_km: float) -> bool:
        return self.min_distance_km <= distance_km <= self.max_distance_km


class PricingRule(BaseModel):
    id: UUID
    name: str
    rule_type: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    adjustment_type: Literal["fixed_cents", "percent"]
    adjustment_amount: int
    priority: int = 100
    active: bool = True
    effective_from: date | None = None
    effective_to: date | None = None

    def in_effect(self, on: date) -> bool:
        if self.effective_from and on < self.effective_from:
            return False
        return not (self.effective_to and on > self.effective_to)


class FeasibilityRule(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    outcome: Literal["allow", "require_manual_approval", "reject"]
    manual_approval_reason: str | None = None
    customer_message: str | None = None
    suggested_alternative: str | None = None
    priority: int = 100
    active: bool = True


class TimeSlot(BaseModel):
    id: UUID
    start_time: str
    end_time: str
    label: str | None = None
    max_orders: int = 3
    active: bool = True
    display_order: int = 0


class Catalog(BaseModel):
    """Everything the engines need, loaded once per request and passed down.

    Lookups are by ID because the language model resolves names to rows before
    anything reaches here — an option that is not in this snapshot cannot be
    priced, quoted or ordered.
    """

    sizes: list[CakeSize] = Field(default_factory=list)
    flavors: list[CakeFlavor] = Field(default_factory=list)
    fillings: list[Filling] = Field(default_factory=list)
    frostings: list[Frosting] = Field(default_factory=list)
    styles: list[DesignStyle] = Field(default_factory=list)
    decorations: list[Decoration] = Field(default_factory=list)
    dietary_options: list[DietaryOption] = Field(default_factory=list)
    delivery_zones: list[DeliveryZone] = Field(default_factory=list)
    pricing_rules: list[PricingRule] = Field(default_factory=list)
    feasibility_rules: list[FeasibilityRule] = Field(default_factory=list)
    time_slots: list[TimeSlot] = Field(default_factory=list)

    def size(self, item_id: UUID | None) -> CakeSize | None:
        return _by_id(self.sizes, item_id)

    def flavor(self, item_id: UUID | None) -> CakeFlavor | None:
        return _by_id(self.flavors, item_id)

    def filling(self, item_id: UUID | None) -> Filling | None:
        return _by_id(self.fillings, item_id)

    def frosting(self, item_id: UUID | None) -> Frosting | None:
        return _by_id(self.frostings, item_id)

    def style(self, item_id: UUID | None) -> DesignStyle | None:
        return _by_id(self.styles, item_id)

    def decoration_list(self, ids: list[UUID]) -> list[Decoration]:
        return [d for d in self.decorations if d.id in set(ids)]

    def dietary_list(self, ids: list[UUID]) -> list[DietaryOption]:
        return [d for d in self.dietary_options if d.id in set(ids)]

    def zone_for(self, distance_km: float) -> DeliveryZone | None:
        """Smallest active zone covering the distance.

        Sorted so overlapping zone boundaries resolve to the cheaper zone
        rather than whichever row happened to come back first.
        """
        candidates = [z for z in self.delivery_zones if z.active and z.covers(distance_km)]
        return min(candidates, key=lambda z: z.max_distance_km) if candidates else None

    def size_for_servings(self, servings: int) -> CakeSize | None:
        """Recommended size for a guest count.

        Exact band match first; otherwise the smallest size that still feeds
        everyone, because under-catering a party is the worse failure.
        """
        active = sorted((s for s in self.sizes if s.active), key=lambda s: s.max_servings)
        for size in active:
            if size.fits(servings):
                return size
        for size in active:
            if size.max_servings >= servings:
                return size
        return active[-1] if active else None


def _by_id(items: list, item_id: UUID | None):
    if item_id is None:
        return None
    return next((i for i in items if i.id == item_id), None)
