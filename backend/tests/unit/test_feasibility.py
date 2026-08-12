"""Feasibility engine tests.

This engine decides whether an order can be confirmed automatically or has to
reach Mayan. A false "allow" means an impossible cake enters production; a
false "reject" means a lost sale. Both directions are tested.
"""

from __future__ import annotations

from datetime import date

from app.schemas.specification import CakeSpecification
from app.services.feasibility.engine import (
    check_catalog_consistency,
    check_feasibility,
)
from catalog_fixture import (
    DECO_COMPLEX_FIGURE,
    DECO_FRESH_FLOWERS,
    DECO_SUGAR_FLOWERS,
    DIET_NUT_FREE,
    FILLING_VANILLA_CREAM,
    FLAVOR_VANILLA,
    FROSTING_BUTTERCREAM,
    FROSTING_WHIPPED,
    SIZE_EVENT,
    SIZE_MEDIUM,
    SIZE_THREE_TIER,
    STYLE_MINIMALIST,
)


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


# ------------------------------------------------------------- the happy path

def test_ordinary_cake_is_allowed(catalog):
    result = check_feasibility(spec(), catalog, lead_time_hours=200, complexity_level=1,
                               total_price_cents=26000)
    assert result.outcome == "allow"
    assert result.manual_approval_reasons == []


def test_sugar_flowers_alone_do_not_need_approval(catalog):
    """Fully edible decoration — the food-safety rule must not fire."""
    result = check_feasibility(
        spec(decoration_ids=[DECO_SUGAR_FLOWERS]), catalog,
        lead_time_hours=200, complexity_level=2, total_price_cents=31000,
    )
    assert result.outcome == "allow"


# ------------------------------------------------------------------ rejection

def test_more_than_three_tiers_is_rejected_with_an_alternative(catalog):
    result = check_feasibility(spec(number_of_tiers=4), catalog, lead_time_hours=200)
    assert result.outcome == "reject"
    assert result.customer_messages
    # Spec section 19: offer an alternative, do not just refuse.
    assert result.alternatives


def test_below_minimum_lead_time_is_rejected(catalog):
    result = check_feasibility(spec(), catalog, lead_time_hours=12)
    assert result.outcome == "reject"
    assert any("24 hours" in m for m in result.customer_messages)


def test_rejection_outranks_manual_approval(catalog):
    """A 4-tier rush order hits both. The strictest outcome must win."""
    result = check_feasibility(spec(number_of_tiers=4), catalog, lead_time_hours=12)
    assert result.outcome == "reject"


# ----------------------------------------------------------- manual approval

def test_three_tier_cake_needs_approval(catalog):
    result = check_feasibility(
        spec(size_id=SIZE_THREE_TIER, servings=90, number_of_tiers=3), catalog,
        lead_time_hours=200, complexity_level=4, total_price_cents=140000,
    )
    assert result.outcome == "require_manual_approval"
    assert any("Three-tier" in r for r in result.manual_approval_reasons)


def test_over_80_servings_needs_approval(catalog):
    result = check_feasibility(spec(size_id=SIZE_EVENT, servings=95), catalog,
                               lead_time_hours=200, complexity_level=3)
    assert result.outcome == "require_manual_approval"
    assert any("80 servings" in r for r in result.manual_approval_reasons)


def test_price_above_ceiling_needs_approval(catalog):
    result = check_feasibility(spec(), catalog, lead_time_hours=200,
                               complexity_level=1, total_price_cents=150001)
    assert result.outcome == "require_manual_approval"


def test_price_exactly_at_ceiling_is_allowed(catalog):
    """Boundary: the rule is 'above', not 'at'."""
    result = check_feasibility(spec(), catalog, lead_time_hours=200,
                               complexity_level=1, total_price_cents=150000)
    assert result.outcome == "allow"


def test_rush_between_24_and_48_hours_needs_approval(catalog):
    result = check_feasibility(spec(), catalog, lead_time_hours=30, complexity_level=1)
    assert result.outcome == "require_manual_approval"
    assert any("Rush" in r for r in result.manual_approval_reasons)


def test_fresh_flowers_need_a_barrier_and_offer_sugar_flowers(catalog):
    result = check_feasibility(spec(decoration_ids=[DECO_FRESH_FLOWERS]), catalog,
                               lead_time_hours=200, complexity_level=2)
    assert result.outcome == "require_manual_approval"
    assert any("Sugar flowers" in a for a in result.alternatives)


def test_complex_figure_needs_approval(catalog):
    result = check_feasibility(spec(decoration_ids=[DECO_COMPLEX_FIGURE]), catalog,
                               lead_time_hours=200, complexity_level=3)
    assert result.outcome == "require_manual_approval"


def test_complexity_level_4_needs_approval(catalog):
    result = check_feasibility(spec(), catalog, lead_time_hours=200, complexity_level=4)
    assert result.outcome == "require_manual_approval"


# ------------------------------------------------------------------ transport

def test_whipped_cream_beyond_its_range_needs_approval(catalog):
    """Cross-field comparison: distance 8 km vs the frosting's 5 km limit."""
    result = check_feasibility(
        spec(frosting_id=FROSTING_WHIPPED, fulfillment_method="delivery"), catalog,
        lead_time_hours=200, delivery_distance_km=8.0, complexity_level=1,
    )
    assert result.outcome == "require_manual_approval"
    assert any("Buttercream" in a for a in result.alternatives)


def test_whipped_cream_within_range_is_fine(catalog):
    result = check_feasibility(
        spec(frosting_id=FROSTING_WHIPPED, fulfillment_method="delivery"), catalog,
        lead_time_hours=200, delivery_distance_km=3.0, complexity_level=1,
    )
    assert result.outcome == "allow"


def test_whipped_cream_for_pickup_is_never_restricted(catalog):
    result = check_feasibility(
        spec(frosting_id=FROSTING_WHIPPED, fulfillment_method="pickup"), catalog,
        lead_time_hours=200, complexity_level=1,
    )
    assert result.outcome == "allow"


def test_buttercream_has_no_distance_limit(catalog):
    result = check_feasibility(
        spec(fulfillment_method="delivery"), catalog,
        lead_time_hours=200, delivery_distance_km=18.0, complexity_level=1,
    )
    assert result.outcome == "allow"


def test_delivery_beyond_20km_needs_approval(catalog):
    result = check_feasibility(
        spec(fulfillment_method="delivery"), catalog,
        lead_time_hours=200, delivery_distance_km=25.0, complexity_level=1,
    )
    assert result.outcome == "require_manual_approval"


# ------------------------------------------------------------------- allergens

def test_allergen_notes_trigger_review(catalog):
    result = check_feasibility(
        spec(allergen_notes=["severe peanut allergy"]), catalog,
        lead_time_hours=200, complexity_level=1,
    )
    assert result.outcome == "require_manual_approval"


def test_nut_free_request_alone_does_not_block(catalog):
    """A preference is not a declared medical allergy."""
    result = check_feasibility(
        spec(dietary_requirement_ids=[DIET_NUT_FREE]), catalog,
        lead_time_hours=200, complexity_level=1,
    )
    assert result.outcome == "allow"


def test_medical_guarantee_request_is_escalated(catalog):
    result = check_feasibility(
        spec(free_text="Can you guarantee allergen free? It must be medically safe."),
        catalog, lead_time_hours=200, complexity_level=1,
    )
    assert result.outcome == "require_manual_approval"
    assert any("allergen guarantee" in r.lower() for r in result.manual_approval_reasons)


# ----------------------------------------------------------------- free text

def test_suspended_structure_from_free_text_is_escalated(catalog):
    result = check_feasibility(
        spec(free_text="I want the top tier to look suspended in mid air"),
        catalog, lead_time_hours=200, complexity_level=2,
    )
    assert result.outcome == "require_manual_approval"
    assert any("rigid stand" in a for a in result.alternatives)


def test_inscription_is_searched_too(catalog):
    """Customers hide requirements in the inscription field as well."""
    result = check_feasibility(
        spec(inscription="Floating dreams"), catalog, lead_time_hours=200, complexity_level=1
    )
    assert result.outcome == "require_manual_approval"


def test_ordinary_words_do_not_trigger_keyword_rules(catalog):
    result = check_feasibility(
        spec(free_text="Something elegant with soft colours, nothing too sweet"),
        catalog, lead_time_hours=200, complexity_level=1,
    )
    assert result.outcome == "allow"


# ------------------------------------------------------------- rule accounting

def test_every_matching_reason_is_recorded(catalog):
    """Mayan needs the full list, not just the first reason found."""
    result = check_feasibility(
        spec(size_id=SIZE_THREE_TIER, servings=95, number_of_tiers=3,
             decoration_ids=[DECO_FRESH_FLOWERS]),
        catalog, lead_time_hours=30, complexity_level=4, total_price_cents=200000,
    )
    assert len(result.manual_approval_reasons) >= 4


def test_deactivated_rules_do_not_fire(catalog):
    for rule in catalog.feasibility_rules:
        rule.active = False
    result = check_feasibility(spec(number_of_tiers=4), catalog, lead_time_hours=1)
    assert result.outcome == "allow"


# ----------------------------------------------------------- consistency check

def test_size_too_small_for_guest_count_is_reported(catalog):
    problems = check_catalog_consistency(spec(servings=40), catalog)
    assert any("serves up to 20" in p for p in problems)


def test_consistent_specification_has_no_problems(catalog):
    assert check_catalog_consistency(spec(), catalog) == []
