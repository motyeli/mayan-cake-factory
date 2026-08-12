"""Condition evaluator shared by the pricing and feasibility rule tables.

Both tables store `conditions` as JSON in the same shape, so this is written
once. Rules are DATA: Mayan can add "no mirror glaze in July" from the admin
panel without a deployment, and without anyone editing Python.

Grammar:

    {"field": "servings", "op": "gt", "value": 80}
    {"all": [ {...}, {...} ]}          every branch must match
    {"any": [ {...}, {...} ]}          at least one branch must match
    {}                                  always true

Operators:

    eq neq gt gte lt lte    numeric or string comparison
    is_true is_false        boolean flags
    is_set                  value is present and not empty
    contains_any            context value (str or list) contains any of value
    gt_field / lt_field     compare against ANOTHER context field, e.g.
                            delivery_distance_km > frosting_max_delivery_km

An unknown operator or a missing field evaluates to False. A rule that cannot
be understood must never fire — silently applying a surcharge or silently
rejecting an order is far worse than ignoring a malformed rule.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

Context = dict[str, Any]


def evaluate(condition: dict[str, Any] | None, context: Context) -> bool:
    if not condition:
        return True

    if "all" in condition:
        return all(evaluate(branch, context) for branch in condition["all"])
    if "any" in condition:
        return any(evaluate(branch, context) for branch in condition["any"])

    field = condition.get("field")
    op = condition.get("op")
    expected = condition.get("value")

    if not field or not op:
        logger.warning("malformed rule condition ignored", extra={"rule_condition_keys": list(condition)})
        return False

    actual = context.get(field)

    try:
        return _apply(op, actual, expected, context)
    except (TypeError, ValueError):
        # Comparing a string to a number, for example. Do not fire.
        return False


def _apply(op: str, actual: Any, expected: Any, context: Context) -> bool:
    if op == "is_set":
        return actual is not None and actual != "" and actual != []
    if op == "is_true":
        return bool(actual) is True
    if op == "is_false":
        return bool(actual) is False

    if op == "contains_any":
        if actual is None:
            return False
        needles = expected if isinstance(expected, list) else [expected]
        if isinstance(actual, str):
            haystack = actual.lower()
            return any(str(n).lower() in haystack for n in needles)
        if isinstance(actual, list | tuple | set):
            lowered = {str(a).lower() for a in actual}
            return any(str(n).lower() in lowered for n in needles)
        return False

    if op in ("gt_field", "lt_field", "gte_field", "lte_field"):
        other = context.get(str(expected))
        if actual is None or other is None:
            return False
        if op == "gt_field":
            return actual > other
        if op == "lt_field":
            return actual < other
        if op == "gte_field":
            return actual >= other
        return actual <= other

    if actual is None:
        return False

    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected

    logger.warning("unknown rule operator ignored", extra={"rule_operator": op})
    return False
