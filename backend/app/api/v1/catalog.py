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


@router.get("", summary="Full public catalog")
async def get_catalog() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for key, (table, columns) in PUBLIC_CATALOG.items():
        rows, _ = await supabase.select(
            table, columns=columns, filters={"active": "eq.true"}, order="display_order"
        )
        result[key] = rows
    return result
