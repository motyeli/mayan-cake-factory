"""Deterministic feasibility (spec section 19).

The AI may propose a design. This engine decides whether it can be produced,
and whether it can be confirmed automatically. The model never overrides it —
it only explains the outcome and offers the stored alternative.

Three outcomes:

    allow                     nothing stands in the way
    require_manual_approval   Mayan decides; the price becomes an estimate
    reject                    cannot be produced as described

`reject` always carries a customer message and, where one exists, a concrete
alternative. Spec section 19: when a request cannot be fulfilled, offer a
feasible alternative instead of only refusing.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.catalog import Catalog
from app.schemas.specification import CakeSpecification
from app.services.rules import evaluate
from pydantic import BaseModel, Field

Outcome = Literal["allow", "require_manual_approval", "reject"]


class RuleHit(BaseModel):
    rule_name: str
    outcome: Outcome
    reason: str | None = None
    customer_message: str | None = None
    suggested_alternative: str | None = None


class FeasibilityResult(BaseModel):
    outcome: Outcome = "allow"
    hits: list[RuleHit] = Field(default_factory=list)

    @property
    def is_rejected(self) -> bool:
        return self.outcome == "reject"

    @property
    def requires_manual_approval(self) -> bool:
        return self.outcome == "require_manual_approval"

    @property
    def manual_approval_reasons(self) -> list[str]:
        return [h.reason for h in self.hits if h.reason and h.outcome != "allow"]

    @property
    def customer_messages(self) -> list[str]:
        return [h.customer_message for h in self.hits if h.customer_message]

    @property
    def alternatives(self) -> list[str]:
        return [h.suggested_alternative for h in self.hits if h.suggested_alternative]


def build_context(
    spec: CakeSpecification,
    catalog: Catalog,
    *,
    lead_time_hours: float | None = None,
    delivery_distance_km: float | None = None,
    total_price_cents: int | None = None,
    complexity_level: int | None = None,
) -> dict:
    """Flatten everything the rules can test into one dictionary.

    Derived booleans are computed here rather than in each rule so a rule row
    stays a simple comparison that Mayan can read and edit.
    """
    decorations = catalog.decoration_list(spec.decoration_ids)
    dietary = catalog.dietary_list(spec.dietary_requirement_ids)
    frosting = catalog.frosting(spec.frosting_id)
    size = catalog.size(spec.size_id)

    tiers = spec.number_of_tiers or (size.tiers if size else 1)

    return {
        "event_type": spec.event_type,
        "servings": spec.servings,
        "number_of_tiers": tiers,
        "shape": spec.shape,
        "complexity_level": complexity_level,
        "total_price_cents": total_price_cents,
        "lead_time_hours": lead_time_hours,
        "fulfillment_method": spec.fulfillment_method,
        "delivery_distance_km": delivery_distance_km,
        "frosting_name": frosting.name if frosting else None,
        "frosting_pickup_only": frosting.pickup_only if frosting else False,
        "frosting_max_delivery_km": frosting.max_delivery_km if frosting else None,
        "decoration_names": [d.name for d in decorations],
        "has_non_food_safe_decoration": any(not d.food_safe for d in decorations),
        "has_manual_approval_decoration": any(d.requires_manual_approval for d in decorations),
        "has_severe_allergy": (
            any(d.severe_allergy_flag for d in dietary) or bool(spec.allergen_notes)
        ),
        "dietary_names": [d.name for d in dietary],
        # Free text plus the inscription: customers describe suspended tiers
        # and demand allergen guarantees in prose, not in structured fields.
        "free_text": " ".join(filter(None, [spec.free_text, spec.inscription])),
        "inscription": spec.inscription,
    }


def check_feasibility(
    spec: CakeSpecification,
    catalog: Catalog,
    *,
    lead_time_hours: float | None = None,
    delivery_distance_km: float | None = None,
    total_price_cents: int | None = None,
    complexity_level: int | None = None,
) -> FeasibilityResult:
    """Evaluate every active rule. Pure: no database, no clock."""
    context = build_context(
        spec,
        catalog,
        lead_time_hours=lead_time_hours,
        delivery_distance_km=delivery_distance_km,
        total_price_cents=total_price_cents,
        complexity_level=complexity_level,
    )

    result = FeasibilityResult()

    # Every matching rule is recorded, not just the first. Mayan needs the
    # full list of reasons on the order, and the customer deserves every
    # relevant explanation rather than one at a time.
    for rule in sorted((r for r in catalog.feasibility_rules if r.active), key=lambda r: r.priority):
        if not evaluate(rule.conditions, context):
            continue
        result.hits.append(
            RuleHit(
                rule_name=rule.name,
                outcome=rule.outcome,
                reason=rule.manual_approval_reason,
                customer_message=rule.customer_message,
                suggested_alternative=rule.suggested_alternative,
            )
        )

    # Strictest outcome wins: one rejection outranks any number of approvals.
    if any(h.outcome == "reject" for h in result.hits):
        result.outcome = "reject"
    elif any(h.outcome == "require_manual_approval" for h in result.hits):
        result.outcome = "require_manual_approval"
    return result


def check_catalog_consistency(spec: CakeSpecification, catalog: Catalog) -> list[str]:
    """Problems with the chosen combination that are not rule-driven.

    These are structural mistakes — a size that cannot feed the guest count,
    a whipped-cream cake being delivered — that would otherwise reach
    production as a surprise.
    """
    problems: list[str] = []

    size = catalog.size(spec.size_id)
    if size and spec.servings and spec.servings > size.max_servings:
        problems.append(
            f"{size.name} serves up to {size.max_servings}, but {spec.servings} guests are expected."
        )

    frosting = catalog.frosting(spec.frosting_id)
    if frosting and frosting.pickup_only and spec.fulfillment_method == "delivery":
        problems.append(f"{frosting.name} is available for collection only.")

    if spec.number_of_tiers and size and spec.number_of_tiers > size.tiers and size.tiers > 1:
        problems.append(f"{size.name} is built as {size.tiers} tiers.")

    return problems
