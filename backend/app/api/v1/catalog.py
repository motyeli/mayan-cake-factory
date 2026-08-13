"""Public catalog reads.

The customer-facing site needs sizes, flavors and styles to render. Serving
them through the backend rather than exposing the database keeps RLS
default-deny intact and gives one place to cache.
"""

from fastapi import APIRouter

from app.core.supabase import supabase

router = APIRouter()

# Catalog tables the public site may read, and the columns it may see.
# Cost prices and manual-approval flags are deliberately not listed.
PUBLIC_CATALOG = {
    "sizes": ("cake_sizes",
              "id,name,description,min_servings,max_servings,base_price_cents,tiers,display_order"),
    "flavors": ("cake_flavors", "id,name,description,price_adjustment_cents,is_premium,display_order"),
    "fillings": ("fillings", "id,name,description,price_adjustment_cents,is_premium,display_order"),
    "frostings": ("frostings",
                  "id,name,description,price_adjustment_cents,pickup_only,max_delivery_km,display_order"),
    "styles": ("design_styles", "id,name,description,price_adjustment_cents,display_order"),
    "decorations": ("decorations", "id,name,description,price_adjustment_cents,display_order"),
    "dietary": ("dietary_options", "id,name,description,price_adjustment_cents,display_order"),
    "combinations": ("recommended_combinations", "id,name,description,display_order"),
}


# Settings the public site may read. An allow-list, not a filter: capacity
# numbers, approval thresholds and internal policy must never leak just
# because someone adds a settings row later.
PUBLIC_SETTINGS = (
    "bakery_name",
    "bakery_address",
    "currency",
    "default_lead_time_hours",
    "min_lead_time_hours",
    "max_revisions",
    "design_link_expiration_days",
    "allergen_disclaimer",
    "visual_disclaimer",
    "inspiration_disclaimer",
    "cancellation_policy",
    "payment_instructions",
)


@router.get("", summary="Full public catalog")
async def get_catalog() -> dict:
    """Everything the public site renders from.

    The site takes its facts from here rather than from copy written into a
    template, so a lead time or a cancellation policy cannot say one thing on
    the home page and another in the rule engine.
    """
    result: dict = {}
    for key, (table, columns) in PUBLIC_CATALOG.items():
        rows, _ = await supabase.select(
            table, columns=columns, filters={"active": "eq.true"}, order="display_order"
        )
        result[key] = rows

    zones, _ = await supabase.select(
        "delivery_zones",
        columns="id,name,min_distance_km,max_distance_km,delivery_fee_cents,requires_manual_approval,display_order",
        filters={"active": "eq.true"},
        order="display_order",
    )
    result["delivery_zones"] = zones

    slots, _ = await supabase.select(
        "time_slots",
        columns="id,start_time,end_time,label,display_order",
        filters={"active": "eq.true"},
        order="display_order",
    )
    result["time_slots"] = slots

    rows, _ = await supabase.select("settings", columns="key,value")
    result["settings"] = {
        row["key"]: row["value"] for row in rows if row["key"] in PUBLIC_SETTINGS
    }
    return result
