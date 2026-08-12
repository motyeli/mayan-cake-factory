"""Loads the catalog snapshot the engines run against.

Cached for a short time because the catalog changes a few times a month and is
read on every message, price calculation and availability check. The TTL is
short enough that an admin edit shows up while Mayan is still looking at the
screen, which matters more here than shaving the last query.
"""

from __future__ import annotations

import time
from datetime import date

from app.core.logging import get_logger
from app.core.supabase import supabase
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
    TimeSlot,
)
from app.services.availability.rules import DayCapacity

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 60

_cache: tuple[float, Catalog] | None = None

# Table name -> (model, whether inactive rows are filtered out server-side)
_TABLES = (
    ("sizes", "cake_sizes", CakeSize),
    ("flavors", "cake_flavors", CakeFlavor),
    ("fillings", "fillings", Filling),
    ("frostings", "frostings", Frosting),
    ("styles", "design_styles", DesignStyle),
    ("decorations", "decorations", Decoration),
    ("dietary_options", "dietary_options", DietaryOption),
    ("delivery_zones", "delivery_zones", DeliveryZone),
    ("time_slots", "time_slots", TimeSlot),
)


async def load_catalog(*, force: bool = False) -> Catalog:
    global _cache

    if not force and _cache is not None:
        loaded_at, cached = _cache
        if time.monotonic() - loaded_at < CACHE_TTL_SECONDS:
            return cached

    data: dict[str, list] = {}
    for attribute, table, model in _TABLES:
        rows, _ = await supabase.select(
            table, filters={"active": "eq.true"}, order="display_order"
        )
        data[attribute] = [model(**row) for row in rows]

    # Rules are ordered by priority, which is how both engines evaluate them.
    pricing_rows, _ = await supabase.select(
        "pricing_rules", filters={"active": "eq.true"}, order="priority"
    )
    data["pricing_rules"] = [PricingRule(**row) for row in pricing_rows]

    feasibility_rows, _ = await supabase.select(
        "feasibility_rules", filters={"active": "eq.true"}, order="priority"
    )
    data["feasibility_rules"] = [FeasibilityRule(**row) for row in feasibility_rows]

    catalog = Catalog(**data)
    _cache = (time.monotonic(), catalog)
    logger.info(
        "catalog loaded",
        extra={
            "sizes": len(catalog.sizes),
            "decorations": len(catalog.decorations),
            "pricing_rules": len(catalog.pricing_rules),
            "feasibility_rules": len(catalog.feasibility_rules),
        },
    )
    return catalog


def invalidate_catalog_cache() -> None:
    """Called after any admin catalog write so the change is visible at once."""
    global _cache
    _cache = None


async def load_settings() -> dict[str, object]:
    """Operational settings as a plain dict of native values."""
    rows, _ = await supabase.select("settings", columns="key,value,value_type")
    return {row["key"]: row["value"] for row in rows}


def setting_int(settings: dict, key: str, default: int) -> int:
    try:
        return int(settings.get(key, default))
    except (TypeError, ValueError):
        return default


async def load_day_capacity(start: date, end: date) -> dict[date, DayCapacity]:
    """Capacity rows in a window. Missing days are absent by design — the
    availability engine treats them as untouched, full-capacity days."""
    rows, _ = await supabase.select(
        "availability_dates",
        filters={"date": f"gte.{start.isoformat()}", "and": f"(date.lte.{end.isoformat()})"},
        order="date",
    )
    result: dict[date, DayCapacity] = {}
    for row in rows:
        day = date.fromisoformat(row["date"])
        result[day] = DayCapacity(
            date=day,
            max_points=row["max_points"],
            reserved_points=row["reserved_points"],
            max_orders=row.get("max_orders"),
            reserved_orders=row.get("reserved_orders", 0),
            blocked=row.get("blocked", False),
        )
    return result
