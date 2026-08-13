"""Order status transitions.

A pure state machine, so every rule is testable without a database. These are
the guards that stop an order reaching a state the bakery never worked through
— which is how a cake gets marked completed without being made.
"""

from __future__ import annotations

import pytest
from app.services.orders.status import (
    OPENING_STATUSES,
    TERMINAL_STATUSES,
    allowed_transitions,
    can_transition,
    is_open,
    releases_capacity,
    transition_error,
)

# ------------------------------------------------------------ opening states

def test_only_two_opening_statuses_exist():
    """An order opens confirmed or awaiting approval — never draft, and never
    anything a caller chose for itself."""
    assert {"confirmed", "awaiting_bakery_approval"} == OPENING_STATUSES


# ------------------------------------------------------------ the happy path

@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("awaiting_bakery_approval", "confirmed"),
        ("confirmed", "in_production"),
        ("in_production", "ready_for_pickup"),
        ("ready_for_pickup", "completed"),
        ("in_production", "out_for_delivery"),
        ("out_for_delivery", "completed"),
    ],
)
def test_normal_progressions_are_allowed(current, target):
    assert can_transition(current, target)


@pytest.mark.parametrize(
    "status",
    ["confirmed", "in_production", "ready_for_pickup", "out_for_delivery",
     "awaiting_bakery_approval"],
)
def test_anything_live_can_be_cancelled(status):
    assert can_transition(status, "cancelled")


# ------------------------------------------------------------- skipping ahead

def test_an_order_cannot_skip_production():
    """Confirmed straight to completed would hide whether the cake was made."""
    assert not can_transition("confirmed", "completed")
    assert "can only move to" in transition_error("confirmed", "completed")


def test_an_order_cannot_go_backwards():
    assert not can_transition("in_production", "confirmed")


def test_terminal_states_are_final():
    for status in TERMINAL_STATUSES:
        assert allowed_transitions(status) == []
        assert "cannot change status any further" in transition_error(status, "confirmed")


def test_completed_cannot_be_reopened():
    assert not can_transition("completed", "in_production")


def test_cancelled_cannot_be_revived():
    assert not can_transition("cancelled", "confirmed")


# ------------------------------------------------- fulfilment method matters

def test_a_delivery_order_cannot_be_marked_ready_for_collection():
    """Otherwise a delivery is marked ready, collected by nobody, and never
    actually delivered."""
    assert not can_transition("in_production", "ready_for_pickup", "delivery")
    assert "delivery order" in transition_error("in_production", "ready_for_pickup", "delivery")


def test_a_collection_order_cannot_be_sent_out_for_delivery():
    assert not can_transition("in_production", "out_for_delivery", "pickup")
    assert "collection order" in transition_error("in_production", "out_for_delivery", "pickup")


def test_each_method_keeps_its_own_route():
    assert "ready_for_pickup" in allowed_transitions("in_production", "pickup")
    assert "out_for_delivery" in allowed_transitions("in_production", "delivery")


# ------------------------------------------------------------------ messages

def test_repeating_the_current_status_says_so_plainly():
    assert "already" in transition_error("confirmed", "confirmed")


def test_an_unknown_status_is_named():
    assert "not a known order status" in transition_error("confirmed", "teleported")


def test_a_refusal_lists_what_is_possible():
    message = transition_error("confirmed", "completed")
    assert "In production" in message or "Cancelled" in message


# ------------------------------------------------------------------ capacity

def test_cancelling_frees_the_slot():
    assert releases_capacity("confirmed", "cancelled") is True


def test_completing_does_not_free_the_slot():
    """The work was already done that day — handing the points back would
    let the bakery oversell a day it has already baked for."""
    assert releases_capacity("ready_for_pickup", "completed") is False


def test_cancelling_twice_frees_nothing_extra():
    assert releases_capacity("cancelled", "cancelled") is False


@pytest.mark.parametrize("status", ["confirmed", "in_production", "draft"])
def test_live_orders_hold_capacity(status):
    assert is_open(status) is True


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_finished_orders_do_not(status):
    assert is_open(status) is False
