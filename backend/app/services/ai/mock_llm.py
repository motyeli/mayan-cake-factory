"""Deterministic stand-in for the language model.

This is not a stub that echoes text. It genuinely parses a customer message —
dates, guest counts, flavours, colours, inscriptions, dietary needs — so the
entire ordering flow, and every test, runs with no credentials and no network.

Determinism is the point: the same message always yields the same extraction,
so a test that depends on it cannot flake, and a failure is always the code's
fault rather than the model's mood.
"""

from __future__ import annotations

import re
from datetime import date

from app.schemas.specification import FIELD_LABELS
from app.services.ai.providers import (
    AssistantTurn,
    ChatMessage,
    ExtractedSpecification,
)

# Which specification field each extracted attribute satisfies. Used to drop
# questions the customer has just answered.
_ANSWERS = {
    "event_type": "event_type",
    "event_date": "event_date",
    "servings": "servings",
    "size": "size_id",
    "cake_flavor": "cake_flavor_id",
    "filling": "filling_id",
    "frosting": "frosting_id",
    "design_style": "design_style_id",
    "fulfillment_method": "fulfillment_method",
}


def still_missing(missing: list[str], extracted: ExtractedSpecification) -> list[str]:
    """Remove anything this message just answered.

    The caller computes `missing` from the specification as it stood BEFORE
    this message, because extraction has not happened yet. Without this filter
    the assistant asks for the date in the same breath as being told it.
    """
    answered = {
        FIELD_LABELS[field]
        for attribute, field in _ANSWERS.items()
        if getattr(extracted, attribute, None)
    }
    # A guest count resolves the size automatically, so that question goes too.
    if extracted.servings:
        answered.add(FIELD_LABELS["size_id"])
    return [item for item in missing if item not in answered]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_EVENTS = {
    "birthday": "Birthday", "wedding": "Wedding", "engagement": "Engagement",
    "anniversary": "Anniversary", "baby shower": "Baby shower",
    "christening": "Christening", "graduation": "Graduation",
    "corporate": "Corporate event", "company": "Corporate event",
    "retirement": "Retirement", "bar mitzvah": "Bar mitzvah",
    "bat mitzvah": "Bat mitzvah",
}

_FLAVORS = ("vanilla", "chocolate", "red velvet", "lemon", "carrot", "coffee",
            "pistachio", "almond")
_FILLINGS = ("vanilla cream", "chocolate ganache", "salted caramel", "raspberry cream",
             "strawberry cream", "lemon curd", "pistachio cream", "praline",
             "mascarpone cream", "raspberry", "caramel")
_FROSTINGS = ("buttercream", "chocolate ganache", "fondant", "mirror glaze", "whipped cream")
_STYLES = ("minimalist", "floral", "birthday", "luxury", "wedding and engagement",
           "corporate", "photo and illustration", "minimal", "elegant")
_DECORATIONS = ("fresh flowers", "sugar flowers", "macarons", "fresh fruit",
                "chocolate pieces", "edible pearls", "edible gold leaf", "gold leaf",
                "edible image", "corporate logo", "cake topper", "candles",
                "drip design", "custom illustration", "pearls")
_DIETARY = ("vegan", "vegetarian", "gluten-free", "gluten free", "lactose-free",
            "lactose free", "nut-free", "nut free")
_COLORS = ("white", "ivory", "cream", "pink", "light pink", "blush", "red", "burgundy",
           "orange", "peach", "yellow", "gold", "green", "sage", "mint", "blue",
           "navy", "purple", "lilac", "lavender", "black", "silver", "grey", "brown")

_STYLE_ALIASES = {"minimal": "Minimalist", "elegant": "Luxury"}


def _find_first(text: str, options: tuple[str, ...]) -> str | None:
    """Longest match wins, so 'chocolate ganache' beats 'chocolate'."""
    hits = [option for option in options if re.search(rf"\b{re.escape(option)}\b", text)]
    return max(hits, key=len) if hits else None


def _find_all(text: str, options: tuple[str, ...]) -> list[str]:
    found = [o for o in options if re.search(rf"\b{re.escape(o)}\b", text)]
    # Drop any term contained in a longer one already matched.
    return [o for o in found if not any(o != other and o in other for other in found)]


_TIER_WORDS = {"single": 1, "one": 1, "two": 2, "double": 2, "three": 3, "triple": 3,
               "four": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _parse_tiers(text: str) -> int | None:
    """Tier count from "two tiers", "2-tier", "single tier".

    Structural, so it must reach the specification: a revision saying "make it
    two tiers" that only changed the image prompt would show the customer a
    two-tier cake while the order said one, at the wrong price.
    """
    match = re.search(r"\b(single|one|two|double|three|triple|four|[1-4])[- ]?tier\w*\b", text)
    return _TIER_WORDS.get(match.group(1)) if match else None


def _parse_servings(text: str) -> int | None:
    for pattern in (
        r"(\d{1,3})\s*(?:people|guests|persons|servings|portions|slices)",
        r"(?:for|serves?|feeds?)\s+(?:about\s+|around\s+|roughly\s+)?(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:of us|pax)\b",
    ):
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 500:
                return value
    return None


def _parse_date(text: str, today: date) -> str | None:
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        return match.group(0)

    match = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    # "12 September" / "September 12". Scan every candidate rather than
    # taking the first: in "20 people on 12 September" the first numeric
    # pair is "20 people", and stopping there loses the date entirely.
    for match in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\b", text):
        if match.group(2) in _MONTHS:
            return _resolve(int(match.group(1)), _MONTHS[match.group(2)], today)

    for match in re.finditer(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", text):
        if match.group(1) in _MONTHS:
            return _resolve(int(match.group(2)), _MONTHS[match.group(1)], today)

    return None


def _resolve(day: int, month: int, today: date) -> str | None:
    """Nearest future occurrence — "3 February" in August means next year."""
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate.isoformat()
    return None


def _parse_inscription(text: str, raw: str) -> str | None:
    for pattern in (
        r"[\"“]([^\"”]{2,120})[\"”]",
        r"(?:say|says|write|written|reads?|inscription)[:\s]+(?:that\s+)?([A-Za-z0-9 ,!'-]{2,120})",
    ):
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,")
    return None


def extract_from_text(text: str, *, today: date | None = None) -> ExtractedSpecification:
    """Pure extraction — the same input always gives the same output."""
    today = today or date.today()
    raw = text or ""
    lowered = raw.lower()

    extracted = ExtractedSpecification()

    for keyword, label in _EVENTS.items():
        if keyword in lowered:
            extracted.event_type = label
            break

    extracted.event_date = _parse_date(lowered, today)
    extracted.servings = _parse_servings(lowered)
    extracted.tiers = _parse_tiers(lowered)

    flavor = _find_first(lowered, _FLAVORS)
    filling = _find_first(lowered, _FILLINGS)
    frosting = _find_first(lowered, _FROSTINGS)

    # "chocolate ganache" is both a filling and a frosting. Only treat it as a
    # frosting when the sentence talks about the outside of the cake.
    if frosting == "chocolate ganache" and not re.search(
        r"\b(frost|frosting|cover|covered|outside|finish|coating)\b", lowered
    ):
        frosting = None

    if filling and flavor and filling.startswith(flavor) and filling != flavor:
        flavor = None  # "raspberry cream" is a filling, not a cake flavour

    # An unknown word offered as a flavour is reported AS the flavour, so the
    # resolver rejects it and the customer is told what the bakery does make.
    # Without this the mock silently ignores "a durian cake" and the rejection
    # path — the system's main safety guard — is never exercised end to end.
    if flavor is None:
        claimed = re.search(r"\b([a-z]{3,20})[- ]flavou?r(?:ed)?\b", lowered) or re.search(
            r"\bflavou?r(?:ed)?\s+(?:of\s+|with\s+)?([a-z]{3,20})\b", lowered
        )
        if claimed:
            word = claimed.group(1)
            if word not in {"the", "any", "some", "your", "this", "that", "cake", "same"}:
                flavor = word

    extracted.cake_flavor = flavor.title() if flavor else None
    extracted.filling = filling.title() if filling else None
    extracted.frosting = frosting.title() if frosting else None

    # "Birthday" is both an occasion and a design style. In "it's her birthday,
    # something floral" the style is Floral — the word birthday is describing
    # the event, not the look. Only fall back to an occasion word as a style
    # when no other style was named.
    style_hits = [s for s in _STYLES if re.search(rf"\b{re.escape(s)}\b", lowered)]
    distinct = [s for s in style_hits if s not in _EVENTS]
    style = max(distinct or style_hits, key=len) if style_hits else None
    if style:
        extracted.design_style = _STYLE_ALIASES.get(style, style.title())

    decoration_hits = _find_all(lowered, _DECORATIONS)
    extracted.decorations = [d.title() for d in decoration_hits]
    extracted.dietary_requirements = [d.title() for d in _find_all(lowered, _DIETARY)]

    # "edible gold leaf" is a decoration. The word gold inside it is not a
    # colour choice, and letting it through overwrote the real palette.
    # Component names are not colour choices. "raspberry cream" put "cream"
    # in the palette and "edible gold leaf" put "gold" there, both overwriting
    # what the customer actually asked for.
    colour_text = lowered
    for hit in [*decoration_hits, flavor, filling, frosting]:
        if hit:
            colour_text = colour_text.replace(hit, " ")
    extracted.colors = _find_all(colour_text, _COLORS)
    extracted.inscription = _parse_inscription(lowered, raw)

    if re.search(r"\b(deliver|delivery|delivered|bring it|send it)\b", lowered):
        extracted.fulfillment_method = "delivery"
    elif re.search(r"\b(pick ?up|collect|collection|come to the|in person)\b", lowered):
        extracted.fulfillment_method = "pickup"

    address = re.search(r"\b\d{1,4}[^,]{3,60},?\s*\d{5}\b[^.]{0,40}", raw)
    if address and extracted.fulfillment_method == "delivery":
        extracted.delivery_address = address.group(0).strip().rstrip(" ?.!,;")

    budget = re.search(r"[$€]\s?(\d{2,5})|\b(?:budget|around|about|up to)\s+(\d{2,5})\b", lowered)
    if budget:
        extracted.customer_budget = float(budget.group(1) or budget.group(2))

    allergy = re.search(r"\b(severe|serious|life[- ]threatening)\s+\w*\s?allerg\w*", lowered)
    if allergy:
        extracted.allergen_notes = [allergy.group(0)]

    return extracted


class MockLLM:
    """Implements both LLMProvider and ExtractionProvider."""

    name = "mock"

    def __init__(self, *, today: date | None = None) -> None:
        self._today = today

    async def converse(
        self,
        *,
        messages: list[ChatMessage],
        catalog_summary: str,
        specification_state: str,
        missing: list[str],
    ) -> AssistantTurn:
        last_customer = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        extracted = extract_from_text(last_customer, today=self._today or date.today())

        remaining = still_missing(missing, extracted)

        if not messages:
            reply = "Tell me about the cake you would like to create."
        elif remaining:
            reply = self._ask_for(remaining)
        else:
            reply = (
                "That gives me everything I need. Here is the full specification — "
                "have a look, and confirm it when you are happy."
            )

        return AssistantTurn(
            reply=reply,
            extracted=extracted,
            suggested_replies=self._suggestions(remaining),
            provider=self.name,
            usage={"mode": "mock"},
        )

    async def extract(
        self, *, messages: list[ChatMessage], current: ExtractedSpecification
    ) -> ExtractedSpecification:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return extract_from_text(last, today=self._today or date.today())

    @staticmethod
    def _ask_for(missing: list[str]) -> str:
        """One or two questions at a time. A checklist of nine reads as a form,
        which is exactly what this product is meant to replace."""
        first = missing[0]
        if len(missing) == 1:
            return f"Almost there — could you tell me {first}?"
        return f"Could you tell me {first}? It would also help to know {missing[1]}."

    @staticmethod
    def _suggestions(missing: list[str]) -> list[str]:
        if not missing:
            return ["Looks good", "I would like to change something"]
        head = missing[0]
        if "occasion" in head:
            return ["A birthday", "A wedding", "A corporate event"]
        if "how many" in head:
            return ["About 10", "About 20", "About 50"]
        if "flavour" in head:
            return ["Vanilla", "Chocolate", "Not sure — what do you suggest?"]
        if "filling" in head:
            return ["Raspberry cream", "Salted caramel", "Whatever suits the flavour"]
        if "finish" in head:
            return ["Buttercream", "Chocolate ganache", "What travels best?"]
        if "style" in head:
            return ["Something floral", "Minimalist", "Elegant and luxurious"]
        if "collection or delivery" in head:
            return ["I will collect it", "Please deliver it"]
        if "date" in head:
            return ["Next Saturday", "In two weeks"]
        return ["Not sure — what do you suggest?"]
