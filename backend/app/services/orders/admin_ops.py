"""Administrative order operations: status changes, approval, overrides.

Everything here writes to the audit log. Spec §34 requires a price override to
record the previous price, the new price, the administrator, the timestamp and
the reason — so the reason is a required argument, not an optional note.
"""

from __future__ import annotations

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.supabase import supabase
from app.security.admin import AdminIdentity
from app.services.orders.status import (
    STATUS_LABELS,
    allowed_transitions,
    releases_capacity,
    transition_error,
)

logger = get_logger(__name__)


async def get_order(order_id: str) -> dict:
    rows, _ = await supabase.select("orders", filters={"id": f"eq.{order_id}"}, limit=1)
    if not rows:
        raise NotFoundError("That order does not exist.")
    return rows[0]


async def audit(
    admin: AdminIdentity | None,
    action: str,
    entity_id: str,
    *,
    previous: dict | None = None,
    new: dict | None = None,
    reason: str | None = None,
    entity_type: str = "order",
) -> None:
    await supabase.insert(
        "audit_log",
        {
            "actor_id": admin.profile_id if admin else None,
            "actor_label": admin.label if admin else "system",
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "previous_data": previous,
            "new_data": new,
            "reason": reason,
        },
    )


async def change_status(
    order_id: str, new_status: str, admin: AdminIdentity, reason: str | None = None
) -> dict:
    order = await get_order(order_id)
    current = order["status"]

    problem = transition_error(current, new_status, order.get("fulfillment_method"))
    if problem:
        raise ConflictError(
            problem,
            {
                "current_status": current,
                "allowed": allowed_transitions(current, order.get("fulfillment_method")),
            },
        )

    updated = await supabase.update(
        "orders", filters={"id": f"eq.{order_id}"}, payload={"status": new_status}
    )

    await supabase.insert(
        "order_status_history",
        {
            "order_id": order_id,
            "previous_status": current,
            "new_status": new_status,
            "changed_by": admin.profile_id,
            "changed_by_label": admin.label,
            "reason": reason,
        },
    )

    # Cancelling hands the production points back so the day can be resold.
    if releases_capacity(current, new_status):
        await supabase.rpc(
            "release_production_capacity",
            {
                "p_date": order["fulfillment_date"],
                "p_points": order["production_points"],
                "p_time_slot_id": order.get("time_slot_id"),
            },
        )
        logger.info(
            "capacity released", extra={"order_number": order["order_number"], "reason": "cancelled"}
        )

    await audit(
        admin,
        "order.status_changed",
        order_id,
        previous={"status": current},
        new={"status": new_status},
        reason=reason,
    )
    logger.info(
        "order status changed",
        extra={"order_number": order["order_number"], "order_status": new_status},
    )
    return updated[0]


async def approve(order_id: str, admin: AdminIdentity, reason: str | None = None) -> dict:
    """Confirm a special order. The estimate becomes a final price."""
    order = await get_order(order_id)
    if order["status"] != "awaiting_bakery_approval":
        raise ConflictError(
            f"This order is {STATUS_LABELS.get(order['status'], order['status']).lower()}, "
            "so there is nothing to approve."
        )

    await supabase.update(
        "orders",
        filters={"id": f"eq.{order_id}"},
        payload={"price_is_estimate": False, "requires_manual_approval": False},
    )
    return await change_status(order_id, "confirmed", admin, reason or "Approved by the bakery")


async def reject(order_id: str, admin: AdminIdentity, reason: str) -> dict:
    """Decline an order. A reason is required — the customer will be told."""
    if not reason or not reason.strip():
        raise ValidationError("Please give a reason for rejecting this order.")
    return await change_status(order_id, "cancelled", admin, reason.strip())


async def override_price(
    order_id: str,
    new_total_cents: int,
    admin: AdminIdentity,
    reason: str,
    new_points: int | None = None,
) -> dict:
    """Manually set the price. Spec §34: every override is recorded with the
    previous price, the new price, who did it, when, and why."""
    if new_total_cents < 0:
        raise ValidationError("A price cannot be negative.")
    if not reason or not reason.strip():
        raise ValidationError("Please give a reason for changing the price.")

    order = await get_order(order_id)
    previous_total = order["total_price_cents"]
    previous_points = order["production_points"]

    payload: dict = {
        "total_price_cents": new_total_cents,
        "amount_due_cents": max(0, new_total_cents - order.get("amount_paid_cents", 0)),
        # An overridden price is a decision, not an estimate.
        "price_is_estimate": False,
    }
    if new_points is not None:
        payload["production_points"] = new_points

    updated = await supabase.update("orders", filters={"id": f"eq.{order_id}"}, payload=payload)

    await supabase.insert(
        "order_price_overrides",
        {
            "order_id": order_id,
            "previous_total_cents": previous_total,
            "new_total_cents": new_total_cents,
            "previous_points": previous_points,
            "new_points": new_points,
            "changed_by": admin.profile_id,
            "changed_by_label": admin.label,
            "reason": reason.strip(),
        },
    )
    await audit(
        admin,
        "order.price_override",
        order_id,
        previous={"total_price_cents": previous_total, "production_points": previous_points},
        new={"total_price_cents": new_total_cents, "production_points": new_points},
        reason=reason.strip(),
    )
    logger.info(
        "order price overridden",
        extra={
            "order_number": order["order_number"],
            "previous_total_cents": previous_total,
            "new_total_cents": new_total_cents,
        },
    )
    return updated[0]


async def add_internal_note(order_id: str, note: str, admin: AdminIdentity) -> dict:
    """Append to the internal notes, never overwrite — an earlier note may be
    the only record of a phone call."""
    order = await get_order(order_id)
    existing = order.get("internal_notes") or ""
    stamped = f"[{admin.full_name}] {note.strip()}"
    combined = f"{existing}\n{stamped}".strip() if existing else stamped

    updated = await supabase.update(
        "orders", filters={"id": f"eq.{order_id}"}, payload={"internal_notes": combined}
    )
    await audit(admin, "order.note_added", order_id, new={"note": stamped})
    return updated[0]
