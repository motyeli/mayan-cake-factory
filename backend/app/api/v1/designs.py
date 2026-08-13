"""Design generation, revisions, version history and approval.

Generation is asynchronous: the endpoint returns a design row immediately with
status "generating" and the client polls the version list. With a real provider
the work takes about a minute, and an HTTP request held open that long is cut
by proxies long before the customer gets an image.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.supabase import supabase
from app.repositories.catalog import load_catalog, load_settings
from app.services import designs as design_service
from app.services import storage
from app.services.ai import conversation, resolver, sessions
from app.services.ai.mock_llm import extract_from_text
from app.services.ai.providers import ExtractedSpecification

logger = get_logger(__name__)

router = APIRouter(prefix="/design-sessions/{token}", tags=["designs"])


@router.post("/generate-design", summary="Create the first design")
async def generate_design(token: str, background: BackgroundTasks) -> dict:
    session = await sessions.get_session(token)

    # Generation costs the bakery money on every call, so the limit is here
    # rather than in the page.
    limiter.hit(
        f"generate:{session['id']}",
        limit=get_settings().rate_limit_generations_per_hour,
        per_seconds=3600,
    )

    existing = await design_service.list_designs(session["id"])
    if existing:
        # A first design already exists; further changes are revisions, which
        # are counted and capped.
        raise ValidationError(
            "A design already exists for this session. Use a revision to change it.",
            {"designs": len(existing)},
        )

    row, prompt = await design_service.create_design_row(session)
    await sessions.touch(session["id"], status="design_generated")

    background.add_task(
        design_service.run_generation, row["id"], prompt, session["id"], row["version_number"]
    )

    settings_rows = await load_settings()
    return {
        "design": {
            "id": row["id"],
            "version_number": row["version_number"],
            "status": "generating",
            "price_cents": row["price_cents"],
        },
        "revisions_remaining": await design_service.check_revision_allowance(session),
        "disclaimer": settings_rows.get("visual_disclaimer"),
        "poll": f"/api/v1/design-sessions/{token}/designs",
    }


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=500)


@router.post("/revisions", summary="Request a change to the design")
async def create_revision(token: str, body: RevisionRequest, background: BackgroundTasks) -> dict:
    session = await sessions.get_session(token)

    # Checked before anything is spent. Raises 409 once the allowance is gone.
    await design_service.check_revision_allowance(session)
    limiter.hit(
        f"generate:{session['id']}",
        limit=get_settings().rate_limit_generations_per_hour,
        per_seconds=3600,
    )

    catalog = await load_catalog()
    settings_rows = await load_settings()

    # A revision is a change to the CAKE, not only to the picture. Re-extract
    # so "make it two tiers" updates the specification, the price and the
    # feasibility verdict — not just the prompt (spec section 21).
    spec = conversation.row_to_spec(await sessions.get_specification_row(session["id"]))
    extracted: ExtractedSpecification = extract_from_text(body.instruction)
    resolution = resolver.resolve(extracted, catalog, current=spec)
    spec = resolution.specification

    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)
    await sessions.save_specification(
        session["id"], conversation.spec_to_row(spec, price, feasibility)
    )

    row, prompt = await design_service.create_design_row(session, revision_request=body.instruction)

    used = int(session.get("revision_count") or 0) + 1
    await sessions.touch(session["id"], revision_count=used)

    background.add_task(
        design_service.run_generation, row["id"], prompt, session["id"], row["version_number"]
    )

    maximum = int(settings_rows.get("max_revisions", 3))
    return {
        "design": {
            "id": row["id"],
            "version_number": row["version_number"],
            "status": "generating",
            "price_cents": row["price_cents"],
        },
        "revisions_used": used,
        "revisions_remaining": max(0, maximum - used),
        "price": price.model_dump(mode="json"),
        "feasibility": feasibility.model_dump(mode="json"),
        "specification_display": conversation.specification_display(spec, catalog),
        "unresolved": resolution.unresolved,
        "poll": f"/api/v1/design-sessions/{token}/designs",
    }


@router.get("/designs", summary="All design versions")
async def list_designs(token: str) -> dict:
    session = await sessions.get_session(token)
    settings_rows = await load_settings()
    maximum = int(settings_rows.get("max_revisions", 3))
    used = int(session.get("revision_count") or 0)

    versions = await design_service.list_designs(session["id"])
    return {
        "designs": versions,
        "revisions_used": used,
        "revisions_remaining": max(0, maximum - used),
        "max_revisions": maximum,
        "disclaimer": settings_rows.get("visual_disclaimer"),
        "approved_design_id": next(
            (d["id"] for d in versions if d.get("customer_approved")), None
        ),
    }


@router.post("/designs/{design_id}/approve", summary="Approve a design version")
async def approve(token: str, design_id: str) -> dict:
    session = await sessions.get_session(token)
    design = await design_service.approve_design(session, design_id)
    return {
        "approved": True,
        "design_id": design["id"],
        "version_number": design["version_number"],
        "price_cents": design["price_cents"],
        "image_url": await storage.signed_url(design.get("image_storage_path")),
    }


@router.post("/uploads", summary="Upload an inspiration or personal image")
async def upload_asset(
    token: str,
    file: UploadFile = File(...),
    asset_type: str = Form("inspiration"),
) -> dict:
    session = await sessions.get_session(token)
    limiter.hit(f"upload:{session['id']}", limit=15, per_seconds=3600)

    if asset_type not in ("inspiration", "personal_photo", "logo", "illustration"):
        raise ValidationError("That upload type is not recognised.")

    data = await file.read()
    stored = await storage.store_customer_upload(
        session["id"], data, file.filename or "upload", file.content_type or ""
    )

    rows = await supabase.insert(
        "uploaded_assets",
        {
            "session_id": session["id"],
            "asset_type": asset_type,
            "storage_path": f"{stored.bucket}/{stored.path}",
            "mime_type": stored.mime_type,
            "original_filename": (file.filename or "upload")[:200],
            "file_size": stored.size,
        },
    )

    settings_rows = await load_settings()
    return {
        "id": rows[0]["id"],
        "asset_type": asset_type,
        "url": await storage.signed_url(f"{stored.bucket}/{stored.path}"),
        # Stated on every upload, not buried in terms: an inspiration image is
        # a direction, never a promise to copy it (spec section 17).
        "disclaimer": settings_rows.get("inspiration_disclaimer"),
    }
