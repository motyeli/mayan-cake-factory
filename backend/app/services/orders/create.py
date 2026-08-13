"""Order creation.

The last gate before a commitment exists. Everything is re-checked here from
the database rather than trusted from the request: the price is recalculated,
feasibility is re-run, the delivery zone is re-derived from the address, and
capacity is reserved inside the same transaction as the insert.

A customer who tampers with the submitted price gets the real one. A customer
who sat on the confirmation screen for an hour while the day filled up gets a
409 rather than an overbooked Saturday.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, EmailStr, Field

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.supabase import supabase
from app.repositories.catalog import load_catalog, load_settings, setting_int
from app.services.ai import conversation, sessions
from app.services.availability.rules import compute_lead_time
from app.services.delivery.geo import (
    Coordinates,
    get_maps_provider,
    haversine_km,
    quote_delivery,
)
from app.services.feasibility.engine import check_catalog_consistency, check_feasibility
from app.services.pricing.engine import calculate_price

logger = get_logger(__name__)


class OrderRequest(BaseModel):
    fulfillment_method: str = Field(pattern="^(pickup|delivery)$")
    fulfillment_date: date
    time_slot_id: str | None = None
    delivery_address: str | None = None

    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: EmailStr
    customer_phone: str = Field(min_length=5, max_length=40)
    customer_notes: str | None = Field(default=None, max_length=1000)

    # Recorded, not merely gating the button. Spec §31 step 18 requires the
    # customer to accept these before an order exists.
    accepts_allergen_notice: bool
    accepts_image_notice: bool
    accepts_policies: bool


class OrderResult(BaseModel):
    order_number: str
    status: str
    total_cents: int
    is_estimate: bool
    requires_manual_approval: bool
    manual_approval_reasons: list[str] = Field(default_factory=list)


async def create_order(session: dict, request: OrderRequest) -> OrderResult:
    settings = get_settings()
    catalog = await load_catalog()
    settings_rows = await load_settings()

    if not (request.accepts_allergen_notice and request.accepts_image_notice
            and request.accepts_policies):
        raise ValidationError(
            "Please accept the allergen, image and policy notices before ordering."
        )

    spec_row = await sessions.get_specification_row(session["id"])
    spec = conversation.row_to_spec(spec_row)
    if not spec_row or spec.missing_information():
        raise ConflictError(
            "Some details are still missing from this design.",
            {"missing_information": spec.missing_labels()},
        )

    # The approved design is the thing being ordered. Without one there is
    # nothing for the bakery to make.
    designs, _ = await supabase.select(
        "cake_designs",
        columns="id,version_number,price_cents",
        filters={"session_id": f"eq.{session['id']}", "customer_approved": "is.true"},
        limit=1,
    )
    if not designs:
        raise ConflictError("Please approve a design before placing the order.")
    approved = designs[0]

    # The customer may have chosen a different method or date than the one in
    # the conversation, so the request wins for fulfilment.
    spec.fulfillment_method = request.fulfillment_method
    if request.delivery_address:
        spec.delivery_address = request.delivery_address

    # --- delivery, re-derived from the address -----------------------------
    delivery_fee = 0
    distance = None
    zone_id = None
    latitude = longitude = None

    if request.fulfillment_method == "delivery":
        if not request.delivery_address:
            raise ValidationError("A delivery address is needed for a delivery order.")

        geocoded = get_maps_provider(settings.maps_provider).geocode(request.delivery_address)
        if not geocoded.confident or geocoded.coordinates is None:
            raise ValidationError(
                geocoded.note or "We could not confirm that delivery address."
            )

        origin = Coordinates(latitude=settings.bakery_latitude, longitude=settings.bakery_longitude)
        distance = haversine_km(origin, geocoded.coordinates)
        quote = quote_delivery(distance, catalog)
        delivery_fee = quote.fee_cents
        zone_id = str(quote.zone.id) if quote.zone else None
        latitude = geocoded.coordinates.latitude
        longitude = geocoded.coordinates.longitude

    # --- lead time, measured to the collection window ----------------------
    slot_start = None
    if request.time_slot_id:
        slot = next((s for s in catalog.time_slots if str(s.id) == request.time_slot_id), None)
        if slot is None:
            raise ValidationError("That time window is not available.")
        slot_start = time.fromisoformat(slot.start_time[:5])

    lead = compute_lead_time(
        request.fulfillment_date,
        now=datetime.now(ZoneInfo(settings.default_timezone)),
        timezone=settings.default_timezone,
        standard_hours=setting_int(settings_rows, "default_lead_time_hours", 48),
        minimum_hours=setting_int(settings_rows, "min_lead_time_hours", 24),
        slot_start=slot_start,
    )

    # --- price and feasibility, recalculated, never taken from the request --
    price = calculate_price(
        spec,
        catalog,
        lead_time_hours=lead.hours,
        delivery_fee_cents=delivery_fee,
        currency=str(settings_rows.get("currency", settings.default_currency)),
    )
    feasibility = check_feasibility(
        spec,
        catalog,
        lead_time_hours=lead.hours,
        delivery_distance_km=distance,
        total_price_cents=price.total_cents,
        complexity_level=price.complexity_level,
    )

    if feasibility.outcome == "reject":
        raise ConflictError(
            feasibility.customer_messages[0]
            if feasibility.customer_messages
            else "This order cannot be produced as described.",
            {"alternatives": feasibility.alternatives},
        )

    problems = check_catalog_consistency(spec, catalog)
    if problems:
        raise ConflictError(" ".join(problems))

    reasons = list(feasibility.manual_approval_reasons)
    if not lead.can_auto_confirm:
        reasons.append("Less than the minimum lead time")

    needs_approval = bool(reasons) or feasibility.outcome != "allow"
    status = "awaiting_bakery_approval" if needs_approval else "confirmed"

    # --- commit: capacity reservation and the order in one transaction -----
    payload = {
        "status": status,
        "fulfillment_method": request.fulfillment_method,
        "fulfillment_date": request.fulfillment_date.isoformat(),
        "time_slot_id": request.time_slot_id,
        "delivery_address": request.delivery_address,
        "delivery_latitude": latitude,
        "delivery_longitude": longitude,
        "delivery_zone_id": zone_id,
        "delivery_distance_km": round(distance, 2) if distance is not None else None,
        "subtotal_cents": price.cake_subtotal_cents,
        "surcharge_cents": price.surcharge_cents,
        "delivery_fee_cents": price.delivery_fee_cents,
        "discount_cents": 0,
        "total_price_cents": price.total_cents,
        "currency": price.currency,
        "price_breakdown": price.model_dump(mode="json"),
        "price_is_estimate": needs_approval or price.is_estimate,
        "payment_method": "pay_on_delivery" if request.fulfillment_method == "delivery"
                          else "pay_at_pickup",
        "complexity_level": price.complexity_level,
        "production_points": price.production_points,
        "is_rush_order": lead.is_rush,
        "requires_manual_approval": needs_approval,
        "manual_approval_reasons": reasons,
        "has_allergen_warning": bool(spec.allergen_notes),
        "customer_name": request.customer_name,
        "customer_email": str(request.customer_email),
        "customer_phone": request.customer_phone,
        "customer_notes": request.customer_notes,
        "design_session_id": session["id"],
        "approved_design_id": approved["id"],
    }

    # Raises ConflictError (409) if the day filled while the customer was
    # deciding — mapped from the plpgsql DATE_FULL / TIME_SLOT_FULL errors.
    result = await supabase.rpc("create_order_atomic", {"payload": payload})

    logger.info(
        "order created",
        extra={
            "order_number": result["order_number"],
            "order_status": status,
            "total_price_cents": price.total_cents,
            "production_points": price.production_points,
            "is_rush_order": lead.is_rush,
        },
    )

    return OrderResult(
        order_number=result["order_number"],
        status=status,
        total_cents=price.total_cents,
        is_estimate=payload["price_is_estimate"],
        requires_manual_approval=needs_approval,
        manual_approval_reasons=reasons,
    )


async def get_order_for_customer(order_number: str) -> dict:
    """Public order view. Deliberately narrow: internal notes, production
    points and approval reasons are the bakery's, not the customer's."""
    rows, _ = await supabase.select(
        "orders",
        columns=(
            "id,order_number,status,fulfillment_method,fulfillment_date,time_slot_id,"
            "delivery_address,total_price_cents,currency,price_breakdown,price_is_estimate,"
            "payment_status,approved_design_id,design_session_id,created_at"
        ),
        filters={"order_number": f"eq.{order_number}"},
        limit=1,
    )
    if not rows:
        raise NotFoundError("We could not find an order with that number.")
    return rows[0]
