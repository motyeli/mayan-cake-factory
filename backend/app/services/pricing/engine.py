"""Deterministic pricing.

The language model NEVER calculates a price (spec section 24). It may read a
breakdown back to the customer, but every figure here comes from catalog rows
and pricing rules in the database.

Order of operations, from spec section 24:

    base price by size
  + premium flavour / filling / frosting / style
  + decoration charges
  + dietary surcharges
  ------------------------------------------  cake subtotal
  x complexity multiplier                      (applies to the cake only)
  + rush surcharge                             (on cake + complexity)
  + delivery fee                               (never multiplied)
  ------------------------------------------  total

Delivery is added last and is never multiplied by complexity or rush: driving
across Paris does not get harder because the cake has sugar flowers on it.

All arithmetic is integer cents. Percentages are basis points.
"""

from __future__ import annotations

from datetime import date

from app.schemas.catalog import Catalog
from app.schemas.specification import CakeSpecification
from app.services.rules import evaluate
from pydantic import BaseModel, Field

# Complexity multipliers are seeded as pricing rules so Mayan can change them.
# These are the fallbacks if a rule row is missing, matching spec section 24.
DEFAULT_COMPLEXITY_BP: dict[int, int] = {1: 0, 2: 2000, 3: 5000, 4: 5000}


class PriceLine(BaseModel):
    label: str
    amount_cents: int
    kind: str = "item"  # item | multiplier | fee


class PriceBreakdown(BaseModel):
    """A transparent breakdown — spec section 6 requires the customer sees it."""

    lines: list[PriceLine] = Field(default_factory=list)
    cake_subtotal_cents: int = 0
    complexity_surcharge_cents: int = 0
    rush_surcharge_cents: int = 0
    delivery_fee_cents: int = 0
    total_cents: int = 0
    complexity_level: int = 1
    production_points: int = 1
    currency: str = "USD"
    is_estimate: bool = False

    @property
    def surcharge_cents(self) -> int:
        return self.complexity_surcharge_cents + self.rush_surcharge_cents


def apply_basis_points(amount_cents: int, basis_points: int) -> int:
    """Percentage of an integer amount, rounded half up.

    Integer-only so money never touches a float. Truncating instead would
    quietly lose a cent per line, which shows up as a mismatched total.
    """
    if basis_points == 0:
        return 0
    return (amount_cents * basis_points + 5000) // 10000


def compute_complexity_level(spec: CakeSpecification, catalog: Catalog) -> int:
    """Complexity 1-4 (spec section 24).

    Derived from the design style, the decoration workload and the structure.
    Deterministic, so the same specification always prices the same.
    """
    style = catalog.style(spec.design_style_id)
    level = style.base_complexity_level if style else 1

    decorations = catalog.decoration_list(spec.decoration_ids)
    decoration_points = sum(d.complexity_points for d in decorations)
    if decoration_points >= 6:
        level = max(level, 3)
    elif decoration_points >= 3:
        level = max(level, 2)
    elif decoration_points >= 1:
        level = max(level, 2) if len(decorations) >= 3 else level

    # Anything the bakery has flagged as hand-work is premium at least.
    if any(d.requires_manual_approval for d in decorations):
        level = max(level, 3)

    tiers = spec.number_of_tiers or (catalog.size(spec.size_id).tiers if catalog.size(spec.size_id) else 1)
    if tiers >= 3:
        level = 4  # special project — never priced automatically
    elif tiers == 2:
        level = max(level, 2)

    if spec.servings and spec.servings > 80:
        level = max(level, 3)

    return min(level, 4)


def compute_production_points(spec: CakeSpecification, catalog: Catalog) -> int:
    """Oven and hand time, in the points the capacity engine reserves.

    Summed from catalog rows rather than guessed from the complexity level, so
    Mayan can say "sugar flowers cost me an extra point" and have it be true.
    """
    size = catalog.size(spec.size_id)
    points = size.production_points if size else 1

    for item in (
        catalog.flavor(spec.cake_flavor_id),
        catalog.filling(spec.filling_id),
        catalog.frosting(spec.frosting_id),
        catalog.style(spec.design_style_id),
    ):
        if item:
            points += item.production_points

    points += sum(d.production_points for d in catalog.decoration_list(spec.decoration_ids))
    points += sum(d.production_points for d in catalog.dietary_list(spec.dietary_requirement_ids))
    return max(1, points)


def _rule_context(
    spec: CakeSpecification,
    catalog: Catalog,
    complexity_level: int,
    lead_time_hours: float | None,
    cake_subtotal_cents: int,
) -> dict:
    frosting = catalog.frosting(spec.frosting_id)
    return {
        "complexity_level": complexity_level,
        "servings": spec.servings,
        "number_of_tiers": spec.number_of_tiers,
        "lead_time_hours": lead_time_hours,
        "fulfillment_method": spec.fulfillment_method,
        "frosting_name": frosting.name if frosting else None,
        "cake_subtotal_cents": cake_subtotal_cents,
    }


def calculate_price(
    spec: CakeSpecification,
    catalog: Catalog,
    *,
    lead_time_hours: float | None = None,
    delivery_fee_cents: int = 0,
    currency: str = "USD",
    today: date | None = None,
) -> PriceBreakdown:
    """Price a specification. Pure: no database, no clock beyond `today`."""
    today = today or date.today()
    breakdown = PriceBreakdown(currency=currency)

    size = catalog.size(spec.size_id)
    if size is None:
        # Nothing can be priced without a size. Return an empty breakdown
        # rather than inventing a number.
        return breakdown

    subtotal = size.base_price_cents
    breakdown.lines.append(PriceLine(label=f"{size.name} base", amount_cents=size.base_price_cents))

    for item, prefix in (
        (catalog.flavor(spec.cake_flavor_id), "Flavour"),
        (catalog.filling(spec.filling_id), "Filling"),
        (catalog.frosting(spec.frosting_id), "Finish"),
        (catalog.style(spec.design_style_id), "Style"),
    ):
        if item and item.price_adjustment_cents:
            subtotal += item.price_adjustment_cents
            breakdown.lines.append(
                PriceLine(label=f"{prefix}: {item.name}", amount_cents=item.price_adjustment_cents)
            )

    for decoration in catalog.decoration_list(spec.decoration_ids):
        if decoration.price_adjustment_cents:
            subtotal += decoration.price_adjustment_cents
            breakdown.lines.append(
                PriceLine(label=decoration.name, amount_cents=decoration.price_adjustment_cents)
            )

    for dietary in catalog.dietary_list(spec.dietary_requirement_ids):
        if dietary.price_adjustment_cents:
            subtotal += dietary.price_adjustment_cents
            breakdown.lines.append(
                PriceLine(label=dietary.name, amount_cents=dietary.price_adjustment_cents)
            )

    complexity_level = compute_complexity_level(spec, catalog)
    context = _rule_context(spec, catalog, complexity_level, lead_time_hours, subtotal)

    # Database-driven surcharges that are not tied to a single catalog row
    # (fondant on large cakes, seasonal adjustments Mayan adds later).
    for rule in sorted(
        (r for r in catalog.pricing_rules if r.active and r.in_effect(today)),
        key=lambda r: r.priority,
    ):
        if rule.rule_type in ("complexity", "rush"):
            continue  # applied below, against the correct base
        if not evaluate(rule.conditions, context):
            continue
        amount = (
            rule.adjustment_amount
            if rule.adjustment_type == "fixed_cents"
            else apply_basis_points(subtotal, rule.adjustment_amount)
        )
        if amount:
            subtotal += amount
            breakdown.lines.append(PriceLine(label=rule.name, amount_cents=amount))

    breakdown.cake_subtotal_cents = subtotal

    # --- complexity, on the cake only -----------------------------------
    complexity_bp = _matching_bp(catalog, "complexity", context, today)
    if complexity_bp is None:
        complexity_bp = DEFAULT_COMPLEXITY_BP.get(complexity_level, 0)
    if complexity_bp:
        surcharge = apply_basis_points(subtotal, complexity_bp)
        breakdown.complexity_surcharge_cents = surcharge
        breakdown.lines.append(
            PriceLine(
                label=f"Complexity level {complexity_level}",
                amount_cents=surcharge,
                kind="multiplier",
            )
        )

    # --- rush, on cake + complexity ---------------------------------------
    rush_base = subtotal + breakdown.complexity_surcharge_cents
    rush_bp = _matching_bp(catalog, "rush", context, today)
    if rush_bp:
        surcharge = apply_basis_points(rush_base, rush_bp)
        breakdown.rush_surcharge_cents = surcharge
        breakdown.lines.append(
            PriceLine(label="Rush order", amount_cents=surcharge, kind="multiplier")
        )

    # --- delivery, never multiplied ---------------------------------------
    if delivery_fee_cents:
        breakdown.delivery_fee_cents = delivery_fee_cents
        breakdown.lines.append(
            PriceLine(label="Delivery", amount_cents=delivery_fee_cents, kind="fee")
        )

    breakdown.complexity_level = complexity_level
    breakdown.production_points = compute_production_points(spec, catalog)
    breakdown.total_cents = (
        breakdown.cake_subtotal_cents
        + breakdown.complexity_surcharge_cents
        + breakdown.rush_surcharge_cents
        + breakdown.delivery_fee_cents
    )
    # Level 4 is never a final price (spec section 24).
    breakdown.is_estimate = complexity_level >= 4
    return breakdown


def _matching_bp(catalog: Catalog, rule_type: str, context: dict, today: date) -> int | None:
    """Highest-priority matching percent rule of a type.

    Rush has two overlapping rules (under 48h and under 24h); priority decides
    which applies, and they must not stack — a 24-hour order is not charged
    20% and 35%.
    """
    for rule in sorted(
        (r for r in catalog.pricing_rules if r.active and r.rule_type == rule_type and r.in_effect(today)),
        key=lambda r: r.priority,
    ):
        if evaluate(rule.conditions, context):
            return rule.adjustment_amount if rule.adjustment_type == "percent" else None
    return None
