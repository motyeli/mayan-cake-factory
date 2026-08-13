"""Order status transitions (spec §35).

A pure state machine. Every transition is validated here and recorded in
`order_status_history`, so "how did this order get to cancelled?" always has an
answer.

Two things this deliberately does NOT allow:

- Skipping states. An order cannot jump from confirmed straight to completed,
  because that would hide whether the cake was actually made.
- Collecting a delivery, or delivering a collection. The fulfilment method
  decides which of `ready_for_pickup` and `out_for_delivery` is reachable at
  all, so a delivery order cannot be marked ready for collection and then
  quietly never delivered.
"""

from __future__ import annotations

from typing import Literal

OrderStatus = Literal[
    "draft",
    "design_in_progress",
    "awaiting_customer_approval",
    "awaiting_bakery_approval",
    "confirmed",
    "in_production",
    "ready_for_pickup",
    "out_for_delivery",
    "completed",
    "cancelled",
]

# The only states an order may open in. Both are set by the rule engine, never
# by the caller (enforced again in create_order_atomic).
OPENING_STATUSES: frozenset[str] = frozenset({"confirmed", "awaiting_bakery_approval"})

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})

_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"design_in_progress", "cancelled"}),
    "design_in_progress": frozenset({"awaiting_customer_approval", "cancelled"}),
    "awaiting_customer_approval": frozenset(
        {"awaiting_bakery_approval", "confirmed", "cancelled"}
    ),
    "awaiting_bakery_approval": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"in_production", "cancelled"}),
    "in_production": frozenset({"ready_for_pickup", "out_for_delivery", "cancelled"}),
    "ready_for_pickup": frozenset({"completed", "cancelled"}),
    "out_for_delivery": frozenset({"completed", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}

# Human wording for the admin UI and the audit trail.
STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "design_in_progress": "Design in progress",
    "awaiting_customer_approval": "Awaiting customer approval",
    "awaiting_bakery_approval": "Awaiting bakery approval",
    "confirmed": "Confirmed",
    "in_production": "In production",
    "ready_for_pickup": "Ready for pickup",
    "out_for_delivery": "Out for delivery",
    "completed": "Completed",
    "cancelled": "Cancelled",
}


def allowed_transitions(current: str, fulfillment_method: str | None = None) -> list[str]:
    """Statuses reachable from `current`, filtered by fulfilment method."""
    options = set(_TRANSITIONS.get(current, frozenset()))

    if fulfillment_method == "delivery":
        options.discard("ready_for_pickup")
    elif fulfillment_method == "pickup":
        options.discard("out_for_delivery")

    return sorted(options)


def can_transition(current: str, target: str, fulfillment_method: str | None = None) -> bool:
    return target in allowed_transitions(current, fulfillment_method)


def transition_error(current: str, target: str, fulfillment_method: str | None = None) -> str | None:
    """Why a transition is refused, phrased for a person. None when allowed."""
    if current == target:
        return f"The order is already {STATUS_LABELS.get(current, current)}."

    if current in TERMINAL_STATUSES:
        return (
            f"This order is {STATUS_LABELS.get(current, current).lower()} and cannot "
            "change status any further."
        )

    if target not in _TRANSITIONS:
        return f"'{target}' is not a known order status."

    if target in _TRANSITIONS.get(current, frozenset()):
        # Known status, reachable in principle — so the fulfilment method is
        # what blocked it.
        if target == "ready_for_pickup" and fulfillment_method == "delivery":
            return "This is a delivery order, so it cannot be marked ready for collection."
        if target == "out_for_delivery" and fulfillment_method == "pickup":
            return "This is a collection order, so it cannot be sent out for delivery."
        return None

    options = allowed_transitions(current, fulfillment_method)
    readable = ", ".join(STATUS_LABELS.get(o, o) for o in options) or "nothing"
    return (
        f"An order that is {STATUS_LABELS.get(current, current).lower()} can only move to: "
        f"{readable}."
    )


def is_open(status: str) -> bool:
    """Still occupying production capacity."""
    return status not in TERMINAL_STATUSES


def releases_capacity(previous: str, new: str) -> bool:
    """Whether this transition should hand the slot back.

    Only cancellation frees capacity — completing an order does not, because
    the work was already done on that day.
    """
    return new == "cancelled" and previous != "cancelled"
