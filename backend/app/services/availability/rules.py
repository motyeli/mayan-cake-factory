"""Lead time, rush classification and capacity arithmetic.

Pure functions. The actual reservation is a database transaction
(`reserve_production_capacity`), because only the database can make the
check-and-book atomic. What lives here is the arithmetic that decides whether
a booking should be attempted at all, and what to offer when it cannot be.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


class LeadTime(BaseModel):
    hours: float
    is_rush: bool
    below_minimum: bool
    can_auto_confirm: bool


def compute_lead_time(
    fulfillment_date: date,
    *,
    now: datetime,
    timezone: str = "Europe/Paris",
    standard_hours: int = 48,
    minimum_hours: int = 24,
    slot_start: time | None = None,
) -> LeadTime:
    """Hours between now and fulfilment, and what that implies.

    Measured to the START of the collection window, not to midnight: a cake
    for a 10:00 pickup must be finished by 10:00, and treating the deadline as
    end-of-day would let an order through with ten hours less notice than the
    rule intends.
    """
    zone = ZoneInfo(timezone)
    deadline = datetime.combine(fulfillment_date, slot_start or time(0, 0), tzinfo=zone)
    reference = now.astimezone(zone)

    hours = (deadline - reference).total_seconds() / 3600.0

    below_minimum = hours < minimum_hours
    is_rush = hours < standard_hours
    return LeadTime(
        hours=round(hours, 2),
        is_rush=is_rush,
        below_minimum=below_minimum,
        # Under the minimum is never auto-confirmed (spec section 30). A rush
        # order above the minimum still can be, if no other rule objects.
        can_auto_confirm=not below_minimum,
    )


class DayCapacity(BaseModel):
    date: date
    max_points: int
    reserved_points: int
    max_orders: int | None = None
    reserved_orders: int = 0
    blocked: bool = False

    @property
    def remaining_points(self) -> int:
        return max(0, self.max_points - self.reserved_points)

    def can_fit(self, points: int) -> bool:
        if self.blocked or points > self.remaining_points:
            return False
        return not (self.max_orders is not None and self.reserved_orders + 1 > self.max_orders)


class AvailabilityAnswer(BaseModel):
    available: bool
    requested_date: date
    remaining_points: int = 0
    reason: str | None = None
    # Spec section 29: when a date is full, show the next three suitable dates.
    alternative_dates: list[date] = Field(default_factory=list)


def check_date_availability(
    requested: date,
    required_points: int,
    days: dict[date, DayCapacity],
    *,
    default_max_points: int = 10,
    default_max_orders: int | None = 6,
    earliest: date | None = None,
    search_days: int = 45,
    suggestions: int = 3,
) -> AvailabilityAnswer:
    """Can this date take the order, and if not, what can?

    A date with no row has never been booked, so it has full default capacity.
    Materialising every calendar day up front would mean writing rows for
    dates nobody has asked about.
    """

    def capacity_for(day: date) -> DayCapacity:
        return days.get(
            day,
            DayCapacity(
                date=day,
                max_points=default_max_points,
                reserved_points=0,
                max_orders=default_max_orders,
            ),
        )

    requested_capacity = capacity_for(requested)

    if requested_capacity.can_fit(required_points):
        return AvailabilityAnswer(
            available=True,
            requested_date=requested,
            remaining_points=requested_capacity.remaining_points,
        )

    reason = (
        "That date is not available for orders."
        if requested_capacity.blocked
        else "That date is fully booked."
    )

    alternatives: list[date] = []
    start = max(requested, earliest) if earliest else requested
    for offset in range(1, search_days + 1):
        candidate = start + timedelta(days=offset)
        if capacity_for(candidate).can_fit(required_points):
            alternatives.append(candidate)
            if len(alternatives) == suggestions:
                break

    return AvailabilityAnswer(
        available=False,
        requested_date=requested,
        remaining_points=requested_capacity.remaining_points,
        reason=reason,
        alternative_dates=alternatives,
    )


def earliest_orderable_date(
    now: datetime,
    *,
    timezone: str = "Europe/Paris",
    standard_hours: int = 48,
) -> date:
    """First date that clears the standard lead time — the sensible default
    for the date picker, so customers are not offered dates that will be
    rejected the moment they choose one."""
    zone = ZoneInfo(timezone)
    return (now.astimezone(zone) + timedelta(hours=standard_hours)).date()
