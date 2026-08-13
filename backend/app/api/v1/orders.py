"""Customer-facing order endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.supabase import supabase
from app.repositories.catalog import load_catalog, load_settings
from app.services import storage
from app.services.ai import conversation, sessions
from app.services.orders.create import OrderRequest, create_order, get_order_for_customer

router = APIRouter(tags=["orders"])


@router.post("/design-sessions/{token}/orders", summary="Place the order")
async def place_order(token: str, body: OrderRequest, request: Request) -> dict:
    session = await sessions.get_session(token)
    limiter.hit(f"order:{session['id']}", limit=5, per_seconds=3600)

    result = await create_order(session, body)
    settings_rows = await load_settings()

    return {
        **result.model_dump(),
        # The link the customer keeps. The token is the one they already hold,
        # so nothing new is issued and nothing extra is stored.
        "return_url": f"{get_settings().frontend_url}/orders/{result.order_number}",
        "payment_instructions": settings_rows.get("payment_instructions"),
    }


@router.get("/orders/{order_number}", summary="Look up an order")
async def get_order(order_number: str) -> dict:
    order = await get_order_for_customer(order_number)
    catalog = await load_catalog()
    settings_rows = await load_settings()

    image_url = None
    if order.get("approved_design_id"):
        rows, _ = await supabase.select(
            "cake_designs",
            columns="image_storage_path",
            filters={"id": f"eq.{order['approved_design_id']}"},
            limit=1,
        )
        if rows:
            image_url = await storage.signed_url(rows[0].get("image_storage_path"))

    display = {}
    if order.get("design_session_id"):
        spec_row = await sessions.get_specification_row(order["design_session_id"])
        display = conversation.specification_display(
            conversation.row_to_spec(spec_row), catalog
        )

    slot_label = None
    if order.get("time_slot_id"):
        slot = next((s for s in catalog.time_slots if str(s.id) == order["time_slot_id"]), None)
        slot_label = slot.label if slot else None

    return {
        "order_number": order["order_number"],
        "status": order["status"],
        "fulfillment_method": order["fulfillment_method"],
        "fulfillment_date": order["fulfillment_date"],
        "time_slot": slot_label,
        "delivery_address": order.get("delivery_address"),
        "total_price_cents": order["total_price_cents"],
        "currency": order["currency"],
        "price_breakdown": order.get("price_breakdown"),
        "price_is_estimate": order.get("price_is_estimate"),
        "payment_status": order["payment_status"],
        "specification_display": display,
        "image_url": image_url,
        "return_url": f"{get_settings().frontend_url}/orders/{order['order_number']}",
        "return_link_note": (
            "Keep this link to come back to your order. It stays active for "
            f"{settings_rows.get('design_link_expiration_days', 14)} days."
        ),
        "payment_instructions": settings_rows.get("payment_instructions"),
        "cancellation_policy": settings_rows.get("cancellation_policy"),
        "visual_disclaimer": settings_rows.get("visual_disclaimer"),
    }
