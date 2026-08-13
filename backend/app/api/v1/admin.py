"""Administrative API.

Every route depends on `current_admin`, which requires both a valid Supabase
token and an active `admin_profiles` row. Business logic lives in
`services/orders/admin_ops.py`; these handlers parse and delegate.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.supabase import supabase
from app.repositories.catalog import (
    invalidate_catalog_cache,
    load_settings,
    setting_int,
)
from app.security.admin import AdminIdentity, current_admin, require_owner, sign_in, sign_out
from app.services.orders import admin_ops
from app.services.orders.status import STATUS_LABELS, allowed_transitions

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------------------------------------- auth --

class SignInRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/session", summary="Sign in")
async def create_admin_session(body: SignInRequest) -> dict:
    return await sign_in(body.email, body.password)


@router.delete("/auth/session", summary="Sign out")
async def delete_admin_session(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        sign_out(header[7:].strip())
    return {"signed_out": True}


@router.get("/me", summary="Who am I")
async def whoami(admin: AdminIdentity = Depends(current_admin)) -> dict:
    return {
        "id": admin.profile_id,
        "full_name": admin.full_name,
        "email": admin.email,
        "role": admin.role,
    }


# -------------------------------------------------------------- dashboard --

@router.get("/dashboard", summary="Today at the atelier")
async def dashboard(admin: AdminIdentity = Depends(current_admin)) -> dict:
    """Spec §32.

    Money is reported as four separate figures. Unpaid order value is NOT
    revenue, and collapsing them into one number is the single easiest way to
    make a bakery think it is richer than it is.
    """
    today = date.today()
    week_end = today + timedelta(days=7)
    settings_rows = await load_settings()

    orders, _ = await supabase.select(
        "orders",
        columns=("id,order_number,status,fulfillment_date,fulfillment_method,total_price_cents,"
                 "amount_paid_cents,price_is_estimate,production_points,is_rush_order,"
                 "has_allergen_warning,requires_manual_approval,manual_approval_reasons,"
                 "created_at,customer_id"),
        filters={"fulfillment_date": f"gte.{(today - timedelta(days=1)).isoformat()}"},
        order="fulfillment_date",
        limit=500,
    )

    live = [o for o in orders if o["status"] not in ("cancelled", "completed")]

    def money(rows, field="total_price_cents"):
        return sum(r.get(field) or 0 for r in rows)

    confirmed = [o for o in live if not o.get("price_is_estimate")]
    estimated = [o for o in live if o.get("price_is_estimate")]

    order_value = money(confirmed)
    paid = money(live, "amount_paid_cents")

    # Capacity for the coming week.
    capacity_rows, _ = await supabase.select(
        "availability_dates",
        columns="date,max_points,reserved_points,blocked",
        filters={"date": f"gte.{today.isoformat()}"},
        order="date",
        limit=14,
    )
    default_points = setting_int(settings_rows, "daily_production_points", 10)

    load = []
    for offset in range(7):
        day = today + timedelta(days=offset)
        row = next((c for c in capacity_rows if c["date"] == day.isoformat()), None)
        used = row["reserved_points"] if row else 0
        limit = row["max_points"] if row else default_points
        load.append({
            "date": day.isoformat(),
            "used": used,
            "max": limit,
            "full": used >= limit or bool(row and row["blocked"]),
        })

    awaiting = [o for o in orders if o["status"] == "awaiting_bakery_approval"]

    return {
        "orders_today": len([o for o in orders if o["fulfillment_date"] == today.isoformat()]),
        "orders_this_week": len(
            [o for o in orders if today.isoformat() <= o["fulfillment_date"] <= week_end.isoformat()]
        ),
        "points_used_today": next((d["used"] for d in load if d["date"] == today.isoformat()), 0),
        "points_limit_today": next((d["max"] for d in load if d["date"] == today.isoformat()),
                                   default_points),
        "awaiting_approval": len(awaiting),
        # Four distinct figures — never summed into one "revenue" number.
        "money": {
            "confirmed_order_value_cents": order_value,
            "amount_paid_cents": paid,
            "outstanding_cents": order_value - paid,
            "estimated_special_order_value_cents": money(estimated),
        },
        "production_load": load,
        "awaiting_orders": [
            {
                "order_number": o["order_number"],
                "fulfillment_date": o["fulfillment_date"],
                "total_price_cents": o["total_price_cents"],
                "reasons": o.get("manual_approval_reasons") or [],
            }
            for o in awaiting
        ],
        "allergen_warnings": [
            o["order_number"] for o in live if o.get("has_allergen_warning")
        ],
        "rush_orders": [o["order_number"] for o in live if o.get("is_rush_order")],
    }


# ------------------------------------------------------------------ orders --

@router.get("/orders", summary="Order list with filters")
async def list_orders(
    admin: AdminIdentity = Depends(current_admin),
    status: str | None = None,
    fulfillment_method: str | None = None,
    fulfillment_date_from: date | None = None,
    fulfillment_date_to: date | None = None,
    complexity_level: int | None = None,
    min_price_cents: int | None = None,
    max_price_cents: int | None = None,
    rush_only: bool = False,
    allergen_only: bool = False,
    special_only: bool = False,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "fulfillment_date",
) -> dict:
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    if fulfillment_method:
        filters["fulfillment_method"] = f"eq.{fulfillment_method}"
    if complexity_level:
        filters["complexity_level"] = f"eq.{complexity_level}"
    if rush_only:
        filters["is_rush_order"] = "is.true"
    if allergen_only:
        filters["has_allergen_warning"] = "is.true"
    if special_only:
        filters["requires_manual_approval"] = "is.true"
    if min_price_cents is not None:
        filters["total_price_cents"] = f"gte.{min_price_cents}"

    rows, total = await supabase.select(
        "orders",
        columns=("id,order_number,status,fulfillment_date,fulfillment_method,complexity_level,"
                 "production_points,total_price_cents,currency,price_is_estimate,is_rush_order,"
                 "has_allergen_warning,requires_manual_approval,customer_id,created_at"),
        filters=filters,
        order=f"{order_by}.desc" if order_by == "created_at" else order_by,
        limit=min(limit, 200),
        offset=offset,
        count=True,
    )

    # Customer details live in their own table; attach them for display.
    customer_ids = {r["customer_id"] for r in rows if r.get("customer_id")}
    customers: dict[str, dict] = {}
    if customer_ids:
        found, _ = await supabase.select(
            "customers",
            columns="id,full_name,email,phone",
            filters={"id": f"in.({','.join(customer_ids)})"},
        )
        customers = {c["id"]: c for c in found}

    results = []
    for row in rows:
        customer = customers.get(row.get("customer_id") or "", {})
        if search:
            needle = search.lower()
            haystack = " ".join(
                str(v) for v in [row["order_number"], customer.get("full_name"),
                                 customer.get("email"), customer.get("phone")] if v
            ).lower()
            if needle not in haystack:
                continue
        results.append({**row, "customer": customer, "status_label": STATUS_LABELS.get(row["status"])})

    return {"orders": results, "total": total, "limit": limit, "offset": offset}


@router.get("/orders/{order_id}", summary="Full order detail")
async def order_detail(order_id: str, admin: AdminIdentity = Depends(current_admin)) -> dict:
    order = await admin_ops.get_order(order_id)

    customer = {}
    if order.get("customer_id"):
        rows, _ = await supabase.select(
            "customers", filters={"id": f"eq.{order['customer_id']}"}, limit=1
        )
        customer = rows[0] if rows else {}

    history, _ = await supabase.select(
        "order_status_history",
        filters={"order_id": f"eq.{order_id}"},
        order="created_at.desc",
    )
    overrides, _ = await supabase.select(
        "order_price_overrides",
        filters={"order_id": f"eq.{order_id}"},
        order="created_at.desc",
    )
    audit_rows, _ = await supabase.select(
        "audit_log",
        filters={"entity_type": "eq.order", "entity_id": f"eq.{order_id}"},
        order="created_at.desc",
        limit=50,
    )

    designs, _ = await supabase.select(
        "cake_designs",
        columns="id,version_number,image_storage_path,revision_request,price_cents,customer_approved",
        filters=(
            {"session_id": f"eq.{order['design_session_id']}"}
            if order.get("design_session_id")
            else {"order_id": f"eq.{order_id}"}
        ),
        order="version_number",
    )
    from app.services import storage

    for design in designs:
        design["image_url"] = await storage.signed_url(design.get("image_storage_path"))

    return {
        "order": order,
        "customer": customer,
        "designs": designs,
        "status_history": history,
        "price_overrides": overrides,
        "audit_log": audit_rows,
        "allowed_transitions": [
            {"status": s, "label": STATUS_LABELS.get(s, s)}
            for s in allowed_transitions(order["status"], order.get("fulfillment_method"))
        ],
    }


class StatusChange(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=500)


@router.post("/orders/{order_id}/status", summary="Change order status")
async def change_status(
    order_id: str, body: StatusChange, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    return await admin_ops.change_status(order_id, body.status, admin, body.reason)


class ApprovalRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.post("/orders/{order_id}/approve", summary="Approve a special order")
async def approve_order(
    order_id: str, body: ApprovalRequest, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    return await admin_ops.approve(order_id, admin, body.reason)


class RejectionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/orders/{order_id}/reject", summary="Reject an order")
async def reject_order(
    order_id: str, body: RejectionRequest, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    return await admin_ops.reject(order_id, admin, body.reason)


class PriceOverride(BaseModel):
    total_cents: int = Field(ge=0)
    production_points: int | None = Field(default=None, ge=0, le=20)
    reason: str = Field(min_length=3, max_length=500)


@router.patch("/orders/{order_id}/price", summary="Override the price")
async def override_price(
    order_id: str, body: PriceOverride, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    return await admin_ops.override_price(
        order_id, body.total_cents, admin, body.reason, body.production_points
    )


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


@router.post("/orders/{order_id}/notes", summary="Add an internal note")
async def add_note(
    order_id: str, body: NoteRequest, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    return await admin_ops.add_internal_note(order_id, body.note, admin)


# ----------------------------------------------------------------- catalog --

CATALOG_TABLES = {
    "sizes": "cake_sizes",
    "flavors": "cake_flavors",
    "fillings": "fillings",
    "frostings": "frostings",
    "styles": "design_styles",
    "decorations": "decorations",
    "dietary": "dietary_options",
    "delivery-zones": "delivery_zones",
    "time-slots": "time_slots",
}


def _table(catalog_type: str) -> str:
    from app.core.errors import NotFoundError

    table = CATALOG_TABLES.get(catalog_type)
    if not table:
        raise NotFoundError(f"'{catalog_type}' is not a catalog type.")
    return table


@router.get("/catalog/{catalog_type}", summary="List catalog items")
async def list_catalog(catalog_type: str, admin: AdminIdentity = Depends(current_admin)) -> dict:
    rows, _ = await supabase.select(_table(catalog_type), order="display_order")
    return {"items": rows}


@router.post("/catalog/{catalog_type}", summary="Create a catalog item")
async def create_catalog_item(
    catalog_type: str, payload: dict, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    rows = await supabase.insert(_table(catalog_type), payload)
    invalidate_catalog_cache()
    await admin_ops.audit(admin, "catalog.created", rows[0]["id"], new=payload,
                          entity_type=catalog_type)
    return rows[0]


@router.patch("/catalog/{catalog_type}/{item_id}", summary="Update a catalog item")
async def update_catalog_item(
    catalog_type: str, item_id: str, payload: dict,
    admin: AdminIdentity = Depends(current_admin),
) -> dict:
    table = _table(catalog_type)
    before, _ = await supabase.select(table, filters={"id": f"eq.{item_id}"}, limit=1)
    rows = await supabase.update(table, filters={"id": f"eq.{item_id}"}, payload=payload)
    invalidate_catalog_cache()
    await admin_ops.audit(admin, "catalog.updated", item_id,
                          previous=before[0] if before else None, new=payload,
                          entity_type=catalog_type)
    return rows[0]


@router.delete("/catalog/{catalog_type}/{item_id}", summary="Deactivate a catalog item")
async def delete_catalog_item(
    catalog_type: str, item_id: str, admin: AdminIdentity = Depends(require_owner)
) -> dict:
    """Deactivates rather than deletes. Existing orders reference these rows,
    and a hard delete would break the history of every cake ever made with it."""
    table = _table(catalog_type)
    rows = await supabase.update(table, filters={"id": f"eq.{item_id}"}, payload={"active": False})
    invalidate_catalog_cache()
    await admin_ops.audit(admin, "catalog.deactivated", item_id, entity_type=catalog_type)
    return {"deactivated": True, "item": rows[0] if rows else None}


# ------------------------------------------------------------ availability --

@router.get("/availability", summary="Capacity calendar")
async def admin_availability(
    admin: AdminIdentity = Depends(current_admin), days: int = 60
) -> dict:
    today = date.today()
    rows, _ = await supabase.select(
        "availability_dates",
        filters={"date": f"gte.{today.isoformat()}"},
        order="date",
        limit=days,
    )
    return {"days": rows, "time_slots": (await supabase.select("time_slots", order="display_order"))[0]}


class AvailabilityUpdate(BaseModel):
    max_points: int | None = Field(default=None, ge=0, le=100)
    max_orders: int | None = Field(default=None, ge=0, le=50)
    blocked: bool | None = None
    rush_available: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


@router.patch("/availability/{day}", summary="Set capacity for a date")
async def update_availability(
    day: date, body: AvailabilityUpdate, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    settings_rows = await load_settings()
    payload = body.model_dump(exclude_none=True)

    existing, _ = await supabase.select(
        "availability_dates", filters={"date": f"eq.{day.isoformat()}"}, limit=1
    )
    if existing:
        rows = await supabase.update(
            "availability_dates", filters={"date": f"eq.{day.isoformat()}"}, payload=payload
        )
    else:
        rows = await supabase.insert(
            "availability_dates",
            {
                "date": day.isoformat(),
                "max_points": setting_int(settings_rows, "daily_production_points", 10),
                "max_orders": setting_int(settings_rows, "max_orders_per_day", 6),
                **payload,
            },
        )

    await admin_ops.audit(admin, "availability.updated", day.isoformat(), new=payload,
                          entity_type="availability")
    return rows[0]


# ---------------------------------------------------------------- settings --

@router.get("/settings", summary="All settings")
async def get_settings_rows(admin: AdminIdentity = Depends(current_admin)) -> dict:
    rows, _ = await supabase.select("settings", order="key")
    return {"settings": rows}


class SettingUpdate(BaseModel):
    value: object


@router.patch("/settings/{key}", summary="Change a setting")
async def update_setting(
    key: str, body: SettingUpdate, admin: AdminIdentity = Depends(require_owner)
) -> dict:
    before, _ = await supabase.select("settings", filters={"key": f"eq.{key}"}, limit=1)
    if not before:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"There is no setting called '{key}'.")

    if not before[0].get("editable", True):
        from app.core.errors import ForbiddenError

        raise ForbiddenError(f"'{key}' cannot be changed from the admin panel.")

    rows = await supabase.update(
        "settings", filters={"key": f"eq.{key}"}, payload={"value": body.value}
    )
    invalidate_catalog_cache()
    await admin_ops.audit(admin, "settings.updated", key,
                          previous={"value": before[0]["value"]}, new={"value": body.value},
                          entity_type="settings")
    return rows[0]


# --------------------------------------------------------------------- crm --

@router.get("/customers", summary="Customer records")
async def list_customers(
    admin: AdminIdentity = Depends(current_admin), search: str | None = None, limit: int = 50
) -> dict:
    rows, total = await supabase.select(
        "customers", order="created_at.desc", limit=min(limit, 200), count=True
    )
    if search:
        needle = search.lower()
        rows = [
            c for c in rows
            if needle in " ".join(
                str(v) for v in [c.get("full_name"), c.get("email"), c.get("phone")] if v
            ).lower()
        ]
    return {"customers": rows, "total": total}


@router.get("/customers/{customer_id}", summary="One customer and their orders")
async def customer_detail(
    customer_id: str, admin: AdminIdentity = Depends(current_admin)
) -> dict:
    from app.core.errors import NotFoundError

    rows, _ = await supabase.select("customers", filters={"id": f"eq.{customer_id}"}, limit=1)
    if not rows:
        raise NotFoundError("That customer does not exist.")

    orders, _ = await supabase.select(
        "orders",
        columns="id,order_number,status,fulfillment_date,total_price_cents,currency",
        filters={"customer_id": f"eq.{customer_id}"},
        order="fulfillment_date.desc",
    )
    return {"customer": rows[0], "orders": orders}


@router.get("/audit-log", summary="Recent administrative actions")
async def audit_log(admin: AdminIdentity = Depends(current_admin), limit: int = 100) -> dict:
    rows, _ = await supabase.select("audit_log", order="created_at.desc", limit=min(limit, 500))
    return {"entries": rows}
