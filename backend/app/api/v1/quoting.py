"""Pricing, availability and delivery endpoints.

Thin handlers: parse, call an engine, return. No business logic lives here
(spec section 43). Every figure returned comes from a deterministic engine over
database rows, never from a language model.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.repositories.catalog import (
    load_catalog,
    load_day_capacity,
    load_settings,
    setting_int,
)
from app.schemas.specification import CakeSpecification
from app.services.availability.rules import (
    check_date_availability,
    compute_lead_time,
    earliest_orderable_date,
)
from app.services.delivery.geo import (
    Coordinates,
    get_maps_provider,
    haversine_km,
    quote_delivery,
)
from app.services.feasibility.engine import check_catalog_consistency, check_feasibility
from app.services.pricing.engine import calculate_price, compute_production_points

router = APIRouter()


def _now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().default_timezone))


def _bakery() -> Coordinates:
    settings = get_settings()
    return Coordinates(latitude=settings.bakery_latitude, longitude=settings.bakery_longitude)


# --------------------------------------------------------------------- pricing


class QuoteRequest(BaseModel):
    specification: CakeSpecification
    fulfillment_date: date | None = None
    delivery_distance_km: float | None = None


class QuoteResponse(BaseModel):
    price: dict
    feasibility: dict
    lead_time: dict | None = None
    consistency_problems: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    can_auto_confirm: bool = False


@router.post("/pricing/calculate", tags=["pricing"], summary="Price a specification")
async def calculate(request: QuoteRequest) -> QuoteResponse:
    catalog = await load_catalog()
    settings_rows = await load_settings()
    spec = request.specification

    fulfillment_date = request.fulfillment_date or spec.event_date
    lead_time = None
    lead_hours = None
    if fulfillment_date:
        lead_time = compute_lead_time(
            fulfillment_date,
            now=_now(),
            timezone=get_settings().default_timezone,
            standard_hours=setting_int(settings_rows, "default_lead_time_hours", 48),
            minimum_hours=setting_int(settings_rows, "min_lead_time_hours", 24),
        )
        lead_hours = lead_time.hours

    delivery_fee = 0
    if spec.fulfillment_method == "delivery" and request.delivery_distance_km is not None:
        delivery_fee = quote_delivery(request.delivery_distance_km, catalog).fee_cents

    price = calculate_price(
        spec,
        catalog,
        lead_time_hours=lead_hours,
        delivery_fee_cents=delivery_fee,
        currency=str(settings_rows.get("currency", get_settings().default_currency)),
    )

    feasibility = check_feasibility(
        spec,
        catalog,
        lead_time_hours=lead_hours,
        delivery_distance_km=request.delivery_distance_km,
        total_price_cents=price.total_cents,
        complexity_level=price.complexity_level,
    )

    # A price is only final when nothing needs a human decision.
    price.is_estimate = price.is_estimate or feasibility.outcome != "allow"

    return QuoteResponse(
        price=price.model_dump(),
        feasibility=feasibility.model_dump(),
        lead_time=lead_time.model_dump() if lead_time else None,
        consistency_problems=check_catalog_consistency(spec, catalog),
        missing_information=spec.missing_labels(),
        can_auto_confirm=(
            spec.is_complete()
            and feasibility.outcome == "allow"
            and bool(lead_time and lead_time.can_auto_confirm)
        ),
    )


# ---------------------------------------------------------------- availability


class AvailabilityRequest(BaseModel):
    requested_date: date
    specification: CakeSpecification | None = None
    production_points: int | None = Field(default=None, ge=1, le=20)


@router.post("/availability/check", tags=["availability"], summary="Check one date")
async def check_availability(request: AvailabilityRequest) -> dict:
    catalog = await load_catalog()
    settings_rows = await load_settings()

    points = request.production_points
    if points is None and request.specification is not None:
        points = compute_production_points(request.specification, catalog)
    points = points or 1

    window_end = request.requested_date + timedelta(days=60)
    days = await load_day_capacity(request.requested_date, window_end)

    answer = check_date_availability(
        request.requested_date,
        points,
        days,
        default_max_points=setting_int(settings_rows, "daily_production_points", 10),
        default_max_orders=setting_int(settings_rows, "max_orders_per_day", 6),
        earliest=earliest_orderable_date(
            _now(),
            timezone=get_settings().default_timezone,
            standard_hours=setting_int(settings_rows, "default_lead_time_hours", 48),
        ),
    )
    return {**answer.model_dump(), "production_points": points}


@router.get("/availability", tags=["availability"], summary="Capacity calendar")
async def availability_calendar(days: int = 45) -> dict:
    settings_rows = await load_settings()
    catalog = await load_catalog()

    default_points = setting_int(settings_rows, "daily_production_points", 10)
    start = earliest_orderable_date(
        _now(),
        timezone=get_settings().default_timezone,
        standard_hours=setting_int(settings_rows, "default_lead_time_hours", 48),
    )
    end = start + timedelta(days=days)
    capacity = await load_day_capacity(start, end)

    calendar = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = capacity.get(day)
        calendar.append(
            {
                "date": day.isoformat(),
                "max_points": row.max_points if row else default_points,
                "reserved_points": row.reserved_points if row else 0,
                "remaining_points": row.remaining_points if row else default_points,
                "blocked": row.blocked if row else False,
            }
        )

    return {
        "earliest_date": start.isoformat(),
        "days": calendar,
        "time_slots": [slot.model_dump(mode="json") for slot in catalog.time_slots],
    }


# --------------------------------------------------------------------- delivery


class DeliveryRequest(BaseModel):
    address: str = Field(min_length=4, max_length=300)


@router.post("/delivery/calculate", tags=["delivery"], summary="Zone and fee for an address")
async def calculate_delivery(request: DeliveryRequest) -> dict:
    catalog = await load_catalog()
    provider = get_maps_provider(get_settings().maps_provider)

    geocoded = provider.geocode(request.address)
    if not geocoded.confident or geocoded.coordinates is None:
        # Not an error: the customer simply needs to give a better address.
        return {
            "deliverable": False,
            "resolved": False,
            "message": geocoded.note,
            "formatted_address": geocoded.formatted_address,
        }

    distance = haversine_km(_bakery(), geocoded.coordinates)
    quote = quote_delivery(distance, catalog)

    return {
        "deliverable": quote.deliverable,
        "resolved": True,
        "formatted_address": geocoded.formatted_address,
        "distance_km": quote.distance_km,
        "zone": quote.zone.model_dump(mode="json") if quote.zone else None,
        "fee_cents": quote.fee_cents,
        "requires_manual_approval": quote.requires_manual_approval,
        "message": quote.message,
        "latitude": geocoded.coordinates.latitude,
        "longitude": geocoded.coordinates.longitude,
    }
