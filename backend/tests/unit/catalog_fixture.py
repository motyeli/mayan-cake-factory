"""Catalog data mirroring the seeded production values.

Values match supabase/migrations/..._seed_data.sql. If a seeded price changes,
these tests should fail — that is the point. A fixture invented independently
of the seed would pass while production prices were wrong.
"""

from __future__ import annotations

import uuid

from app.schemas.catalog import (
    CakeFlavor,
    CakeSize,
    Catalog,
    Decoration,
    DeliveryZone,
    DesignStyle,
    DietaryOption,
    FeasibilityRule,
    Filling,
    Frosting,
    PricingRule,
)


def _id(seed: str) -> uuid.UUID:
    """Stable UUID per name, so tests can refer to items readably."""
    return uuid.uuid5(uuid.NAMESPACE_OID, seed)


SIZE_MINI = _id("Mini")
SIZE_MEDIUM = _id("Medium")
SIZE_EVENT = _id("Event")
SIZE_TWO_TIER = _id("Two-Tier")
SIZE_THREE_TIER = _id("Three-Tier")

FLAVOR_VANILLA = _id("Vanilla")
FLAVOR_PISTACHIO = _id("Pistachio")

FILLING_VANILLA_CREAM = _id("Vanilla cream")
FILLING_RASPBERRY = _id("Raspberry cream")

FROSTING_BUTTERCREAM = _id("Buttercream")
FROSTING_WHIPPED = _id("Whipped cream")
FROSTING_FONDANT = _id("Fondant")

STYLE_MINIMALIST = _id("Minimalist")
STYLE_FLORAL = _id("Floral")
STYLE_LUXURY = _id("Luxury")

DECO_INSCRIPTION = _id("Custom inscription")
DECO_FRESH_FLOWERS = _id("Fresh flowers")
DECO_SUGAR_FLOWERS = _id("Sugar flowers")
DECO_GOLD_LEAF = _id("Edible gold leaf")
DECO_COMPLEX_FIGURE = _id("Complex handmade figure")

DIET_VEGAN = _id("Vegan")
DIET_NUT_FREE = _id("Nut-free request")


def build_catalog() -> Catalog:
    """Fresh instance per call — tests mutate rules to check inactive paths."""
    return Catalog(
        sizes=[
            CakeSize(id=SIZE_MINI, name="Mini", min_servings=6, max_servings=8,
                     base_price_cents=10000, tiers=1, production_points=1),
            CakeSize(id=SIZE_MEDIUM, name="Medium", min_servings=16, max_servings=20,
                     base_price_cents=26000, tiers=1, production_points=2),
            CakeSize(id=SIZE_EVENT, name="Event", min_servings=40, max_servings=50,
                     base_price_cents=70000, tiers=1, production_points=3),
            CakeSize(id=SIZE_TWO_TIER, name="Two-Tier", min_servings=50, max_servings=70,
                     base_price_cents=95000, tiers=2, production_points=3),
            CakeSize(id=SIZE_THREE_TIER, name="Three-Tier", min_servings=70, max_servings=100,
                     base_price_cents=140000, tiers=3, production_points=4,
                     requires_manual_approval=True),
        ],
        flavors=[
            CakeFlavor(id=FLAVOR_VANILLA, name="Vanilla", price_adjustment_cents=0),
            CakeFlavor(id=FLAVOR_PISTACHIO, name="Pistachio", price_adjustment_cents=1500,
                       is_premium=True),
        ],
        fillings=[
            Filling(id=FILLING_VANILLA_CREAM, name="Vanilla cream", price_adjustment_cents=0),
            Filling(id=FILLING_RASPBERRY, name="Raspberry cream", price_adjustment_cents=2000,
                    is_premium=True),
        ],
        frostings=[
            Frosting(id=FROSTING_BUTTERCREAM, name="Buttercream", price_adjustment_cents=0),
            Frosting(id=FROSTING_WHIPPED, name="Whipped cream", price_adjustment_cents=0,
                     max_delivery_km=5),
            Frosting(id=FROSTING_FONDANT, name="Fondant", price_adjustment_cents=4000,
                     production_points=1),
        ],
        styles=[
            DesignStyle(id=STYLE_MINIMALIST, name="Minimalist", base_complexity_level=1),
            DesignStyle(id=STYLE_FLORAL, name="Floral", base_complexity_level=2),
            DesignStyle(id=STYLE_LUXURY, name="Luxury", base_complexity_level=3,
                        price_adjustment_cents=5000),
        ],
        decorations=[
            Decoration(id=DECO_INSCRIPTION, name="Custom inscription", price_adjustment_cents=0),
            Decoration(id=DECO_FRESH_FLOWERS, name="Fresh flowers", price_adjustment_cents=3000,
                       max_price_cents=12000, complexity_points=1, food_safe=False,
                       requires_barrier=True),
            Decoration(id=DECO_SUGAR_FLOWERS, name="Sugar flowers", price_adjustment_cents=5000,
                       max_price_cents=25000, complexity_points=2),
            Decoration(id=DECO_GOLD_LEAF, name="Edible gold leaf", price_adjustment_cents=4000,
                       max_price_cents=10000, complexity_points=1),
            Decoration(id=DECO_COMPLEX_FIGURE, name="Complex handmade figure",
                       price_adjustment_cents=15000, max_price_cents=30000,
                       complexity_points=3, requires_manual_approval=True),
        ],
        dietary_options=[
            DietaryOption(id=DIET_VEGAN, name="Vegan", price_adjustment_cents=3000),
            DietaryOption(id=DIET_NUT_FREE, name="Nut-free request", price_adjustment_cents=0),
        ],
        delivery_zones=[
            DeliveryZone(id=_id("z1"), name="Zone 1", min_distance_km=0, max_distance_km=5,
                         delivery_fee_cents=2500),
            DeliveryZone(id=_id("z2"), name="Zone 2", min_distance_km=5, max_distance_km=10,
                         delivery_fee_cents=4500),
            DeliveryZone(id=_id("z3"), name="Zone 3", min_distance_km=10, max_distance_km=20,
                         delivery_fee_cents=7500),
            DeliveryZone(id=_id("z4"), name="Extended", min_distance_km=20, max_distance_km=100,
                         delivery_fee_cents=0, requires_manual_approval=True),
        ],
        pricing_rules=[
            PricingRule(id=_id("pr-c2"), name="Complexity level 2", rule_type="complexity",
                        conditions={"field": "complexity_level", "op": "eq", "value": 2},
                        adjustment_type="percent", adjustment_amount=2000, priority=10),
            PricingRule(id=_id("pr-c3"), name="Complexity level 3", rule_type="complexity",
                        conditions={"field": "complexity_level", "op": "eq", "value": 3},
                        adjustment_type="percent", adjustment_amount=5000, priority=10),
            PricingRule(id=_id("pr-r48"), name="Rush under 48 hours", rule_type="rush",
                        conditions={"field": "lead_time_hours", "op": "lt", "value": 48},
                        adjustment_type="percent", adjustment_amount=2000, priority=20),
            PricingRule(id=_id("pr-r24"), name="Rush under 24 hours", rule_type="rush",
                        conditions={"field": "lead_time_hours", "op": "lt", "value": 24},
                        adjustment_type="percent", adjustment_amount=3500, priority=19),
            PricingRule(id=_id("pr-fondant"), name="Fondant on large cakes", rule_type="frosting",
                        conditions={"all": [
                            {"field": "frosting_name", "op": "eq", "value": "Fondant"},
                            {"field": "servings", "op": "gte", "value": 40}]},
                        adjustment_type="fixed_cents", adjustment_amount=6000, priority=30),
        ],
        feasibility_rules=[
            FeasibilityRule(id=_id("f-tiers"), name="Unsupported tier count",
                            conditions={"field": "number_of_tiers", "op": "gt", "value": 3},
                            outcome="reject",
                            customer_message=(
                                "Cakes above three tiers cannot be built "
                                "and transported safely."),
                            suggested_alternative="A three-tier cake, or two tiers with matching side cakes.",
                            priority=10),
            FeasibilityRule(id=_id("f-3tier"), name="Three-tier cake",
                            conditions={"field": "number_of_tiers", "op": "gte", "value": 3},
                            outcome="require_manual_approval",
                            manual_approval_reason="Three-tier cake requires bakery approval",
                            priority=20),
            FeasibilityRule(id=_id("f-servings"), name="Large serving count",
                            conditions={"field": "servings", "op": "gt", "value": 80},
                            outcome="require_manual_approval",
                            manual_approval_reason="More than 80 servings requires bakery approval",
                            priority=20),
            FeasibilityRule(id=_id("f-price"), name="Price above ceiling",
                            conditions={"field": "total_price_cents", "op": "gt", "value": 150000},
                            outcome="require_manual_approval",
                            manual_approval_reason="Order value above $1,500 requires bakery approval",
                            priority=30),
            FeasibilityRule(id=_id("f-minlead"), name="Below minimum lead time",
                            conditions={"field": "lead_time_hours", "op": "lt", "value": 24},
                            outcome="reject",
                            customer_message="The bakery needs at least 24 hours of notice.",
                            suggested_alternative="The earliest date with capacity.",
                            priority=10),
            FeasibilityRule(id=_id("f-rush"), name="Rush order under 48 hours",
                            conditions={"all": [
                                {"field": "lead_time_hours", "op": "lt", "value": 48},
                                {"field": "lead_time_hours", "op": "gte", "value": 24}]},
                            outcome="require_manual_approval",
                            manual_approval_reason="Rush order inside the 48 hour lead time",
                            priority=25),
            FeasibilityRule(id=_id("f-frosting"), name="Frosting cannot survive the distance",
                            conditions={"all": [
                                {"field": "fulfillment_method", "op": "eq", "value": "delivery"},
                                {"field": "frosting_max_delivery_km", "op": "is_set", "value": True},
                                {"field": "delivery_distance_km", "op": "gt_field",
                                 "value": "frosting_max_delivery_km"}]},
                            outcome="require_manual_approval",
                            manual_approval_reason="Frosting is not rated for this delivery distance",
                            suggested_alternative=(
                                "Buttercream or chocolate ganache, which travel reliably."),
                            priority=40),
            FeasibilityRule(id=_id("f-flowers"), name="Fresh flowers in contact with food",
                            conditions={"field": "has_non_food_safe_decoration", "op": "is_true",
                                        "value": True},
                            outcome="require_manual_approval",
                            manual_approval_reason="Fresh flowers require a food-safe barrier",
                            suggested_alternative="Sugar flowers, which are fully edible.",
                            priority=50),
            FeasibilityRule(id=_id("f-distance"), name="Delivery beyond standard area",
                            conditions={"field": "delivery_distance_km", "op": "gt", "value": 20},
                            outcome="require_manual_approval",
                            manual_approval_reason="Delivery beyond the standard 20 km area",
                            priority=40),
            FeasibilityRule(id=_id("f-allergy"), name="Severe allergy declared",
                            conditions={"field": "has_severe_allergy", "op": "is_true", "value": True},
                            outcome="require_manual_approval",
                            manual_approval_reason="Severe allergy declared",
                            priority=15),
            FeasibilityRule(id=_id("f-figure"), name="Complex sculpted work",
                            conditions={"field": "has_manual_approval_decoration", "op": "is_true",
                                        "value": True},
                            outcome="require_manual_approval",
                            manual_approval_reason="Complex handmade figure requires bakery approval",
                            priority=35),
            FeasibilityRule(id=_id("f-l4"), name="Special project complexity",
                            conditions={"field": "complexity_level", "op": "gte", "value": 4},
                            outcome="require_manual_approval",
                            manual_approval_reason="Special project — priced by the bakery",
                            priority=30),
            FeasibilityRule(id=_id("f-suspended"), name="Suspended structure",
                            conditions={"field": "free_text", "op": "contains_any",
                                        "value": ["suspended", "floating", "gravity defying"]},
                            outcome="require_manual_approval",
                            manual_approval_reason="Suspended structure requires bakery approval",
                            suggested_alternative="The same effect on a concealed rigid stand.",
                            priority=45),
            FeasibilityRule(id=_id("f-medical"), name="Allergen guarantee requested",
                            conditions={"field": "free_text", "op": "contains_any",
                                        "value": ["guarantee allergen", "medically safe", "anaphyla"]},
                            outcome="require_manual_approval",
                            manual_approval_reason="Medical allergen guarantee requested",
                            priority=5),
        ],
    )
