"""Delivery zones, geocoding, lead time and capacity arithmetic."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from app.services.availability.rules import (
    DayCapacity,
    check_date_availability,
    compute_lead_time,
    earliest_orderable_date,
)
from app.services.delivery.geo import (
    Coordinates,
    MockMapsProvider,
    get_maps_provider,
    haversine_km,
    quote_delivery,
)

PARIS = ZoneInfo("Europe/Paris")
# Near the Eiffel Tower — the bakery's configured origin.
BAKERY = Coordinates(latitude=48.8584, longitude=2.2945)


# ------------------------------------------------------------------ haversine

def test_distance_to_itself_is_zero():
    assert haversine_km(BAKERY, BAKERY) == pytest.approx(0.0, abs=1e-9)


def test_known_distance_is_accurate():
    """Eiffel Tower to Notre-Dame is about 4.1 km in a straight line."""
    notre_dame = Coordinates(latitude=48.8530, longitude=2.3499)
    assert haversine_km(BAKERY, notre_dame) == pytest.approx(4.1, abs=0.3)


def test_distance_is_symmetric():
    other = Coordinates(latitude=48.8362, longitude=2.2451)
    assert haversine_km(BAKERY, other) == pytest.approx(haversine_km(other, BAKERY))


# ------------------------------------------------------------------ geocoding

def test_paris_postcode_geocodes():
    result = MockMapsProvider().geocode("12 Rue de Rivoli, 75004 Paris")
    assert result.confident is True
    assert result.coordinates is not None


def test_address_without_a_postcode_is_not_confident():
    result = MockMapsProvider().geocode("Somewhere near the river")
    assert result.confident is False
    assert result.coordinates is None
    assert "postal code" in result.note


def test_unknown_postcode_is_reported_not_guessed():
    result = MockMapsProvider().geocode("1 Main Street, 99999 Nowhere")
    assert result.confident is False
    assert "99999" in result.note


def test_unimplemented_provider_fails_loudly():
    """Silently falling back to mock distances would under-charge delivery."""
    with pytest.raises(NotImplementedError):
        get_maps_provider("google")


# ----------------------------------------------------------------- zones

@pytest.mark.parametrize(
    ("distance", "expected_fee"),
    [(0.5, 2500), (4.9, 2500), (5.0, 2500), (7.0, 4500), (10.0, 4500), (15.0, 7500)],
)
def test_zone_fees_by_distance(catalog, distance, expected_fee):
    assert quote_delivery(distance, catalog).fee_cents == expected_fee


def test_overlapping_boundaries_resolve_to_the_cheaper_zone(catalog):
    """5.0 km sits in both zone 1 and zone 2; the customer gets zone 1."""
    assert quote_delivery(5.0, catalog).zone.name == "Zone 1"


def test_beyond_20km_is_a_manual_request_not_a_refusal(catalog):
    quote = quote_delivery(25.0, catalog)
    assert quote.requires_manual_approval is True
    assert quote.deliverable is True
    assert quote.fee_cents == 0


def test_past_every_zone_still_offers_a_path(catalog):
    quote = quote_delivery(500.0, catalog)
    assert quote.requires_manual_approval is True
    assert quote.message


def test_full_address_to_fee(catalog):
    """End to end: address -> coordinates -> distance -> zone -> fee."""
    geo = MockMapsProvider().geocode("5 Avenue Anatole France, 75007 Paris")
    distance = haversine_km(BAKERY, geo.coordinates)
    quote = quote_delivery(distance, catalog)
    assert quote.fee_cents == 2500  # same arrondissement as the bakery


def test_versailles_falls_outside_the_standard_area(catalog):
    geo = MockMapsProvider().geocode("Place d'Armes, 78000 Versailles")
    distance = haversine_km(BAKERY, geo.coordinates)
    assert distance > 10
    assert quote_delivery(distance, catalog).fee_cents in (7500, 0)


# --------------------------------------------------------------- lead time

def _now(day: int, hour: int) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=PARIS)


def test_comfortable_lead_time_is_not_rush():
    lead = compute_lead_time(date(2026, 9, 20), now=_now(12, 10))
    assert lead.is_rush is False
    assert lead.can_auto_confirm is True


def test_under_48_hours_is_rush_but_still_confirmable():
    lead = compute_lead_time(date(2026, 9, 14), now=_now(12, 12), slot_start=time(10, 0))
    assert lead.is_rush is True
    assert lead.below_minimum is False
    assert lead.can_auto_confirm is True


def test_under_24_hours_cannot_be_auto_confirmed():
    lead = compute_lead_time(date(2026, 9, 13), now=_now(12, 20), slot_start=time(10, 0))
    assert lead.below_minimum is True
    assert lead.can_auto_confirm is False


def test_lead_time_measures_to_the_slot_not_to_midnight():
    """A 10:00 collection must be ready at 10:00, not at end of day.

    Measuring to midnight would credit an extra 10 hours of notice and let an
    order through with less warning than the rule intends.
    """
    to_slot = compute_lead_time(date(2026, 9, 14), now=_now(12, 12), slot_start=time(10, 0))
    to_midnight = compute_lead_time(date(2026, 9, 14), now=_now(12, 12))
    assert to_slot.hours < to_midnight.hours + 24
    assert to_slot.hours == pytest.approx(46.0, abs=0.1)


def test_earliest_orderable_date_respects_the_standard_lead_time():
    assert earliest_orderable_date(_now(12, 9)) == date(2026, 9, 14)


# ---------------------------------------------------------------- capacity

def test_untouched_date_has_full_default_capacity():
    answer = check_date_availability(date(2026, 9, 20), 3, {})
    assert answer.available is True
    assert answer.remaining_points == 10


def test_date_with_room_accepts_the_order():
    days = {date(2026, 9, 20): DayCapacity(date=date(2026, 9, 20), max_points=10,
                                           reserved_points=6)}
    assert check_date_availability(date(2026, 9, 20), 4, days).available is True


def test_order_that_would_exceed_points_is_refused():
    days = {date(2026, 9, 20): DayCapacity(date=date(2026, 9, 20), max_points=10,
                                           reserved_points=8)}
    answer = check_date_availability(date(2026, 9, 20), 3, days)
    assert answer.available is False
    assert "fully booked" in answer.reason


def test_blocked_date_is_refused_with_its_own_reason():
    days = {date(2026, 9, 20): DayCapacity(date=date(2026, 9, 20), max_points=10,
                                           reserved_points=0, blocked=True)}
    answer = check_date_availability(date(2026, 9, 20), 1, days)
    assert answer.available is False
    assert "not available" in answer.reason


def test_order_count_limit_applies_even_with_points_left():
    days = {date(2026, 9, 20): DayCapacity(date=date(2026, 9, 20), max_points=10,
                                           reserved_points=2, max_orders=6,
                                           reserved_orders=6)}
    assert check_date_availability(date(2026, 9, 20), 1, days).available is False


def test_full_date_offers_the_next_three_available_dates():
    """Spec section 29: when a date is full, show the next three."""
    full = date(2026, 9, 20)
    days = {
        full: DayCapacity(date=full, max_points=10, reserved_points=10),
        date(2026, 9, 21): DayCapacity(date=date(2026, 9, 21), max_points=10,
                                       reserved_points=10),
        date(2026, 9, 22): DayCapacity(date=date(2026, 9, 22), max_points=10,
                                       reserved_points=0, blocked=True),
    }
    answer = check_date_availability(full, 3, days)
    assert answer.available is False
    # 21st full, 22nd blocked, so the first three free days follow those.
    assert answer.alternative_dates == [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)]


def test_alternatives_account_for_the_size_of_the_order():
    """A big cake should not be offered a day that only fits a small one."""
    full = date(2026, 9, 20)
    days = {
        full: DayCapacity(date=full, max_points=10, reserved_points=10),
        date(2026, 9, 21): DayCapacity(date=date(2026, 9, 21), max_points=10,
                                       reserved_points=8),
    }
    answer = check_date_availability(full, 4, days)
    assert date(2026, 9, 21) not in answer.alternative_dates


def test_exact_fit_is_allowed():
    days = {date(2026, 9, 20): DayCapacity(date=date(2026, 9, 20), max_points=10,
                                           reserved_points=7)}
    assert check_date_availability(date(2026, 9, 20), 3, days).available is True
