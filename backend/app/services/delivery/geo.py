"""Delivery distance and zone classification.

A maps provider is abstracted behind `MapsProvider` so a real geocoder can be
dropped in without touching the zone logic. The mock provider is not a stub
that returns 0 — it geocodes real Paris postal codes to their arrondissement
centroids, so zone classification is genuinely correct in development and the
delivery pricing can be tested against real addresses without an API key.

The bakery's own coordinates come from settings, never hard-coded (spec §28).
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from app.schemas.catalog import Catalog, DeliveryZone
from pydantic import BaseModel

EARTH_RADIUS_KM = 6371.0088

# Centroids of Paris arrondissements and the nearest inner suburbs, good to a
# few hundred metres — far finer than the 5/10/20 km zone boundaries need.
PARIS_POSTCODES: dict[str, tuple[float, float]] = {
    "75001": (48.8626, 2.3364), "75002": (48.8680, 2.3417), "75003": (48.8637, 2.3615),
    "75004": (48.8551, 2.3572), "75005": (48.8448, 2.3501), "75006": (48.8496, 2.3327),
    "75007": (48.8565, 2.3125), "75008": (48.8726, 2.3125), "75009": (48.8768, 2.3373),
    "75010": (48.8760, 2.3595), "75011": (48.8580, 2.3793), "75012": (48.8351, 2.4210),
    "75013": (48.8322, 2.3561), "75014": (48.8300, 2.3265), "75015": (48.8412, 2.3003),
    "75016": (48.8637, 2.2769), "75017": (48.8872, 2.3080), "75018": (48.8925, 2.3444),
    "75019": (48.8869, 2.3826), "75020": (48.8639, 2.3985),
    # Inner suburbs, to exercise zones 2 and 3.
    "92100": (48.8362, 2.2451),  # Boulogne-Billancourt
    "92200": (48.8924, 2.2686),  # Neuilly-sur-Seine
    "92300": (48.8918, 2.2381),  # Levallois / Courbevoie edge
    "93100": (48.8637, 2.4483),  # Montreuil
    "94300": (48.8106, 2.4310),  # Vincennes
    "78000": (48.8014, 2.1301),  # Versailles — beyond 20 km
}

_POSTCODE = re.compile(r"\b(\d{5})\b")


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class GeocodeResult(BaseModel):
    formatted_address: str
    coordinates: Coordinates | None = None
    confident: bool = True
    note: str | None = None


class MapsProvider(Protocol):
    """Address validation and geocoding. Swap the implementation via
    MAPS_PROVIDER without touching zone or pricing logic."""

    def geocode(self, address: str) -> GeocodeResult: ...


class MockMapsProvider:
    """Postal-code geocoder for Paris. Correct enough to classify zones."""

    name = "mock"

    def geocode(self, address: str) -> GeocodeResult:
        match = _POSTCODE.search(address or "")
        if not match:
            return GeocodeResult(
                formatted_address=address,
                coordinates=None,
                confident=False,
                note="Please include a postal code so we can confirm the delivery zone.",
            )

        postcode = match.group(1)
        point = PARIS_POSTCODES.get(postcode)
        if point is None:
            return GeocodeResult(
                formatted_address=address,
                coordinates=None,
                confident=False,
                note=f"We do not recognise postal code {postcode} as a Paris delivery area.",
            )

        return GeocodeResult(
            formatted_address=address,
            coordinates=Coordinates(latitude=point[0], longitude=point[1]),
            confident=True,
            note=None,
        )


def haversine_km(origin: Coordinates, destination: Coordinates) -> float:
    """Great-circle distance in kilometres.

    Straight-line, not driving distance. It under-estimates a real route, so
    zone boundaries are slightly generous to the customer — the safe direction
    to be wrong in for a fee, and documented rather than silently assumed.
    """
    lat1, lon1 = math.radians(origin.latitude), math.radians(origin.longitude)
    lat2, lon2 = math.radians(destination.latitude), math.radians(destination.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class DeliveryQuote(BaseModel):
    distance_km: float
    zone: DeliveryZone | None = None
    fee_cents: int = 0
    requires_manual_approval: bool = False
    deliverable: bool = True
    message: str | None = None


def quote_delivery(distance_km: float, catalog: Catalog) -> DeliveryQuote:
    """Zone and fee for a distance. Pure — zones come from the catalog."""
    zone = catalog.zone_for(distance_km)

    if zone is None:
        # Past every configured zone: a special delivery request, not a refusal.
        return DeliveryQuote(
            distance_km=round(distance_km, 2),
            zone=None,
            fee_cents=0,
            requires_manual_approval=True,
            deliverable=True,
            message=(
                "This address is outside our standard delivery area, so delivery "
                "is arranged individually with the bakery."
            ),
        )

    return DeliveryQuote(
        distance_km=round(distance_km, 2),
        zone=zone,
        fee_cents=zone.delivery_fee_cents,
        requires_manual_approval=zone.requires_manual_approval,
        deliverable=True,
        message=(
            "Delivery to this address is arranged individually with the bakery."
            if zone.requires_manual_approval
            else None
        ),
    )


def get_maps_provider(provider_name: str) -> MapsProvider:
    """Only the mock exists today. A real provider slots in here; the calling
    code and the zone rules do not change."""
    if provider_name != "mock":
        # Fail loudly rather than silently degrading to mock distances, which
        # would quietly under-charge for delivery in production.
        raise NotImplementedError(
            f"Maps provider '{provider_name}' is not implemented. "
            "Set MAPS_PROVIDER=mock or add an implementation."
        )
    return MockMapsProvider()
