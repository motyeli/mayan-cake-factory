"""Pricing engine tests.

The engine decides what a customer is charged, so these tests assert exact
cent values rather than "greater than zero". A pricing bug that only shifts a
total slightly is exactly the kind that ships unnoticed.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.schemas.specification import CakeSpecification
from app.services.pricing.engine import (
    apply_basis_points,
    calculate_price,
    compute_complexity_level,
    compute_production_points,
)
from catalog_fixture import (
    DECO_COMPLEX_FIGURE,
    DECO_FRESH_FLOWERS,
    DECO_GOLD_LEAF,
    DECO_INSCRIPTION,
    DECO_SUGAR_FLOWERS,
    DIET_VEGAN,
    FILLING_RASPBERRY,
    FILLING_VANILLA_CREAM,
    FLAVOR_PISTACHIO,
    FLAVOR_VANILLA,
    FROSTING_BUTTERCREAM,
    FROSTING_FONDANT,
    SIZE_EVENT,
    SIZE_MEDIUM,
    SIZE_MINI,
    SIZE_THREE_TIER,
    SIZE_TWO_TIER,
    STYLE_FLORAL,
    STYLE_LUXURY,
    STYLE_MINIMALIST,
)

TODAY = date(2026, 8, 12)


def spec(**overrides) -> CakeSpecification:
    base = {
        "event_type": "Birthday",
        "event_date": date(2026, 9, 12),
        "servings": 20,
        "size_id": SIZE_MEDIUM,
        "cake_flavor_id": FLAVOR_VANILLA,
        "filling_id": FILLING_VANILLA_CREAM,
        "frosting_id": FROSTING_BUTTERCREAM,
        "design_style_id": STYLE_MINIMALIST,
        "fulfillment_method": "pickup",
    }
    base.update(overrides)
    return CakeSpecification(**base)


# ------------------------------------------------------------ basis points

@pytest.mark.parametrize(
    ("amount", "bp", "expected"),
    [
        (10000, 2000, 2000),   # 20% of $100
        (10000, 0, 0),
        (26000, 5000, 13000),  # 50%
        (33333, 2000, 6667),   # rounds half up, not truncated
        (1, 5000, 1),          # half a cent rounds up
    ],
)
def test_apply_basis_points(amount, bp, expected):
    assert apply_basis_points(amount, bp) == expected


def test_basis_points_never_returns_float():
    assert isinstance(apply_basis_points(12345, 1234), int)


# ------------------------------------------------------------------ basics

def test_simplest_cake_is_the_base_price(catalog):
    result = calculate_price(spec(), catalog, today=TODAY)
    assert result.cake_subtotal_cents == 26000
    assert result.complexity_surcharge_cents == 0
    assert result.total_cents == 26000
    assert result.complexity_level == 1


def test_component_surcharges_accumulate(catalog):
    result = calculate_price(
        spec(cake_flavor_id=FLAVOR_PISTACHIO, filling_id=FILLING_RASPBERRY),
        catalog,
        today=TODAY,
    )
    # 26000 base + 1500 pistachio + 2000 raspberry
    assert result.cake_subtotal_cents == 29500
    assert result.total_cents == 29500


def test_missing_size_returns_empty_breakdown_rather_than_guessing(catalog):
    result = calculate_price(spec(size_id=None), catalog, today=TODAY)
    assert result.total_cents == 0
    assert result.lines == []


# --------------------------------------------------------------- complexity

def test_floral_style_is_level_2_and_adds_20_percent(catalog):
    result = calculate_price(spec(design_style_id=STYLE_FLORAL), catalog, today=TODAY)
    assert result.complexity_level == 2
    assert result.complexity_surcharge_cents == 5200  # 20% of 26000
    assert result.total_cents == 31200


def test_luxury_style_is_level_3_and_adds_50_percent(catalog):
    result = calculate_price(spec(design_style_id=STYLE_LUXURY), catalog, today=TODAY)
    assert result.complexity_level == 3
    # 26000 + 5000 style surcharge = 31000, then +50%
    assert result.cake_subtotal_cents == 31000
    assert result.complexity_surcharge_cents == 15500
    assert result.total_cents == 46500


def test_three_tiers_is_always_level_4_and_an_estimate(catalog):
    result = calculate_price(
        spec(size_id=SIZE_THREE_TIER, servings=90, number_of_tiers=3), catalog, today=TODAY
    )
    assert result.complexity_level == 4
    assert result.is_estimate is True


def test_two_tiers_is_at_least_level_2(catalog):
    assert compute_complexity_level(
        spec(size_id=SIZE_TWO_TIER, servings=60, number_of_tiers=2), catalog
    ) == 2


def test_manual_approval_decoration_raises_complexity(catalog):
    assert compute_complexity_level(
        spec(decoration_ids=[DECO_COMPLEX_FIGURE]), catalog
    ) == 3


def test_heavy_decoration_load_raises_complexity(catalog):
    # sugar flowers 2 + gold leaf 1 + fresh flowers 1 = 4 points -> level 2
    level = compute_complexity_level(
        spec(decoration_ids=[DECO_SUGAR_FLOWERS, DECO_GOLD_LEAF, DECO_FRESH_FLOWERS]), catalog
    )
    assert level >= 2


def test_over_80_servings_raises_complexity(catalog):
    assert compute_complexity_level(spec(size_id=SIZE_EVENT, servings=95), catalog) >= 3


# ---------------------------------------------------------------- decorations

def test_decorations_are_charged_then_multiplied(catalog):
    result = calculate_price(
        spec(design_style_id=STYLE_FLORAL,
             decoration_ids=[DECO_FRESH_FLOWERS, DECO_GOLD_LEAF]),
        catalog,
        today=TODAY,
    )
    # 26000 + 3000 flowers + 4000 gold leaf = 33000
    assert result.cake_subtotal_cents == 33000
    assert result.complexity_surcharge_cents == 6600  # 20%
    assert result.total_cents == 39600


def test_free_decorations_do_not_add_a_line(catalog):
    result = calculate_price(spec(decoration_ids=[DECO_INSCRIPTION]), catalog, today=TODAY)
    assert all("inscription" not in line.label.lower() for line in result.lines)
    assert result.total_cents == 26000


def test_dietary_surcharge_is_applied(catalog):
    result = calculate_price(spec(dietary_requirement_ids=[DIET_VEGAN]), catalog, today=TODAY)
    assert result.cake_subtotal_cents == 29000


# ---------------------------------------------------------------------- rush

def test_rush_under_48_hours_adds_20_percent(catalog):
    result = calculate_price(spec(), catalog, lead_time_hours=30, today=TODAY)
    assert result.rush_surcharge_cents == 5200
    assert result.total_cents == 31200


def test_rush_surcharges_do_not_stack(catalog):
    """Under 24h matches both rush rules. Priority must pick one, not both."""
    result = calculate_price(spec(), catalog, lead_time_hours=10, today=TODAY)
    assert result.rush_surcharge_cents == apply_basis_points(26000, 3500)
    assert result.rush_surcharge_cents == 9100


def test_no_rush_surcharge_with_normal_lead_time(catalog):
    result = calculate_price(spec(), catalog, lead_time_hours=200, today=TODAY)
    assert result.rush_surcharge_cents == 0


def test_rush_applies_after_complexity(catalog):
    result = calculate_price(
        spec(design_style_id=STYLE_FLORAL), catalog, lead_time_hours=30, today=TODAY
    )
    # rush is charged on cake + complexity: 26000 + 5200 = 31200, 20% = 6240
    assert result.rush_surcharge_cents == 6240


# ------------------------------------------------------------------ delivery

def test_delivery_fee_is_added_but_never_multiplied(catalog):
    plain = calculate_price(spec(), catalog, today=TODAY)
    with_delivery = calculate_price(
        spec(design_style_id=STYLE_LUXURY), catalog, delivery_fee_cents=2500,
        lead_time_hours=10, today=TODAY,
    )
    assert with_delivery.delivery_fee_cents == 2500
    # The fee appears in the total exactly once, unscaled.
    without_fee = calculate_price(
        spec(design_style_id=STYLE_LUXURY), catalog, lead_time_hours=10, today=TODAY
    )
    assert with_delivery.total_cents - without_fee.total_cents == 2500
    assert plain.delivery_fee_cents == 0


# ------------------------------------------------------------ database rules

def test_conditional_pricing_rule_fires_only_when_matched(catalog):
    """Fondant surcharge applies to large cakes only."""
    large = calculate_price(
        spec(size_id=SIZE_EVENT, servings=45, frosting_id=FROSTING_FONDANT), catalog, today=TODAY
    )
    small = calculate_price(
        spec(size_id=SIZE_MINI, servings=8, frosting_id=FROSTING_FONDANT), catalog, today=TODAY
    )
    # Large: 70000 + 4000 fondant + 6000 rule
    assert large.cake_subtotal_cents == 80000
    # Small: 10000 + 4000 fondant, rule does not fire
    assert small.cake_subtotal_cents == 14000


def test_inactive_rules_are_ignored(catalog):
    for rule in catalog.pricing_rules:
        rule.active = False
    result = calculate_price(spec(design_style_id=STYLE_FLORAL), catalog, lead_time_hours=10,
                             today=TODAY)
    # Falls back to the built-in level 2 multiplier, and no rush rule fires.
    assert result.rush_surcharge_cents == 0
    assert result.complexity_surcharge_cents == 5200


def test_expired_rule_does_not_apply(catalog):
    for rule in catalog.pricing_rules:
        if rule.rule_type == "rush":
            rule.effective_to = date(2026, 1, 1)
    result = calculate_price(spec(), catalog, lead_time_hours=10, today=TODAY)
    assert result.rush_surcharge_cents == 0


# ----------------------------------------------------------- production points

def test_production_points_sum_from_catalog(catalog):
    # Medium size 2 + fondant 1
    assert compute_production_points(spec(frosting_id=FROSTING_FONDANT), catalog) == 3


def test_production_points_never_below_one(catalog):
    assert compute_production_points(spec(size_id=None), catalog) == 1


# --------------------------------------------------------------- consistency

def test_total_always_equals_the_sum_of_its_parts(catalog):
    result = calculate_price(
        spec(design_style_id=STYLE_LUXURY,
             decoration_ids=[DECO_SUGAR_FLOWERS, DECO_GOLD_LEAF],
             dietary_requirement_ids=[DIET_VEGAN]),
        catalog,
        lead_time_hours=30,
        delivery_fee_cents=4500,
        today=TODAY,
    )
    assert result.total_cents == (
        result.cake_subtotal_cents
        + result.complexity_surcharge_cents
        + result.rush_surcharge_cents
        + result.delivery_fee_cents
    )


def test_pricing_is_deterministic(catalog):
    """Same input, same price — twice. The customer is quoted this number."""
    args = {"lead_time_hours": 30, "delivery_fee_cents": 2500, "today": TODAY}
    s = spec(design_style_id=STYLE_FLORAL, decoration_ids=[DECO_GOLD_LEAF])
    first = calculate_price(s, catalog, **args).total_cents
    second = calculate_price(s, catalog, **args).total_cents
    assert first == second
