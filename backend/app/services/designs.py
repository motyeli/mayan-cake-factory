"""Cake design generation, revisions and version history.

Generation takes about a minute with a real provider (measured: 57 s for
gpt-image-1). Holding an HTTP request open that long is fragile — proxies and
load balancers cut it, and the customer sees a dead page. So a design row is
created immediately with `image_storage_path` NULL, the work happens in the
background, and the client polls the version list.

The design row IS the job record. It already has the columns a job needs —
prompt, provider, result id, usage, error_info — so no queue, no Redis, no
second store.

ponytail: FastAPI background tasks, in-process. If the process restarts
mid-generation the row stays pending and the customer regenerates. At five
orders a day that is the right trade; move to a durable queue if generation
volume ever justifies one.
"""

from __future__ import annotations

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.supabase import supabase
from app.repositories.catalog import load_catalog, load_settings, setting_int
from app.schemas.specification import CakeSpecification
from app.services import storage
from app.services.ai import conversation, prompts, sessions
from app.services.ai.factory import get_image_provider

logger = get_logger(__name__)


async def list_designs(session_id: str) -> list[dict]:
    rows, _ = await supabase.select(
        "cake_designs",
        columns=("id,version_number,image_storage_path,revision_request,price_cents,"
                 "customer_approved,error_info,created_at,generation_prompt"),
        filters={"session_id": f"eq.{session_id}"},
        order="version_number",
    )
    for row in rows:
        row["image_url"] = await storage.signed_url(row.get("image_storage_path"))
        # The prompt is internal: it carries the bakery's style hints, and the
        # customer has no use for it.
        row.pop("generation_prompt", None)
        row["status"] = (
            "failed" if row.get("error_info")
            else "ready" if row.get("image_storage_path")
            else "generating"
        )
    return rows


async def _next_version(session_id: str) -> int:
    rows, _ = await supabase.select(
        "cake_designs",
        columns="version_number",
        filters={"session_id": f"eq.{session_id}"},
        order="version_number.desc",
        limit=1,
    )
    return (rows[0]["version_number"] + 1) if rows else 1


async def create_design_row(
    session: dict, *, revision_request: str | None = None
) -> tuple[dict, str]:
    """Reserve a version and return (row, prompt).

    The unique constraint on (session_id, version_number) is the race guard:
    two concurrent requests both compute the same next version and one insert
    fails, so a double-click cannot burn two revisions.
    """
    catalog = await load_catalog()
    settings_rows = await load_settings()

    spec_row = await sessions.get_specification_row(session["id"])
    if not spec_row:
        raise ConflictError("Please tell us about the cake before we design it.")

    spec = conversation.row_to_spec(spec_row)
    if spec.missing_information():
        raise ConflictError(
            "Some details are still needed before we can create a design.",
            {"missing_information": spec.missing_labels()},
        )

    price, feasibility = await conversation.evaluate(spec, catalog, settings_rows)
    if feasibility.outcome == "reject":
        raise ConflictError(
            feasibility.customer_messages[0]
            if feasibility.customer_messages
            else "This design cannot be produced as described.",
            {"alternatives": feasibility.alternatives},
        )

    prompt = prompts.image_prompt(spec, catalog)
    if revision_request:
        prompt = f"{prompt}\n\nRevision requested: {revision_request}"

    version = await _next_version(session["id"])
    rows = await supabase.insert(
        "cake_designs",
        {
            "session_id": session["id"],
            "version_number": version,
            "generation_prompt": prompt,
            "revision_request": revision_request,
            "structured_specification": spec.model_dump(mode="json"),
            "price_cents": price.total_cents,
            "price_breakdown": price.model_dump(mode="json"),
        },
    )
    return rows[0], prompt


async def run_generation(design_id: str, prompt: str, session_id: str, version: int) -> None:
    """Background worker. Never raises — a failure is recorded on the row."""
    provider = get_image_provider()
    try:
        image = await provider.generate(prompt=prompt)
        stored = await storage.store_design(session_id, version, image.data, image.content_type)
        await supabase.update(
            "cake_designs",
            filters={"id": f"eq.{design_id}"},
            payload={
                "image_storage_path": f"{stored.bucket}/{stored.path}",
                "provider": image.provider,
                "provider_result_id": image.provider_result_id,
                "usage_metadata": image.usage,
                "error_info": None,
            },
        )
        logger.info(
            "design generated",
            extra={"design_version": version, "image_provider": image.provider, "bytes": stored.size},
        )
    except Exception as exc:  # background task: record, never crash the worker
        logger.error("design generation failed", extra={"error_type": type(exc).__name__})
        await supabase.update(
            "cake_designs",
            filters={"id": f"eq.{design_id}"},
            payload={"error_info": "generation_failed"},
        )


async def check_revision_allowance(session: dict) -> int:
    """Revisions remaining. Raises when the allowance is spent.

    Enforced here, in the backend, because the frontend counter is a courtesy
    and image generation costs the bakery real money (spec section 21).
    """
    settings_rows = await load_settings()
    maximum = setting_int(settings_rows, "max_revisions", 3)
    used = int(session.get("revision_count") or 0)

    if used >= maximum:
        raise ConflictError(
            f"You have used all {maximum} free revisions. You can choose any earlier "
            "version, start a new design, or ask the bakery to review a special request.",
            {"reason": "REVISION_LIMIT_REACHED", "revisions_used": used, "max_revisions": maximum},
        )
    return maximum - used


async def approve_design(session: dict, design_id: str) -> dict:
    rows, _ = await supabase.select(
        "cake_designs",
        filters={"id": f"eq.{design_id}", "session_id": f"eq.{session['id']}"},
        limit=1,
    )
    if not rows:
        raise NotFoundError("That design version does not exist.")

    design = rows[0]
    if not design.get("image_storage_path"):
        raise ConflictError("That design is still being created. Please wait a moment.")

    # A partial unique index allows only one approved design per session, so
    # the previous approval is cleared first rather than colliding with it.
    await supabase.update(
        "cake_designs",
        filters={"session_id": f"eq.{session['id']}", "customer_approved": "is.true"},
        payload={"customer_approved": False},
    )
    updated = await supabase.update(
        "cake_designs", filters={"id": f"eq.{design_id}"}, payload={"customer_approved": True}
    )
    await sessions.touch(session["id"], status="design_approved")
    logger.info("design approved", extra={"design_version": design["version_number"]})
    return updated[0]


async def specification_for_design(design: dict) -> CakeSpecification:
    """The specification as it was when this version was generated.

    Stored per version, so choosing an earlier design restores the cake that
    was actually shown — not the specification as it drifted afterwards.
    """
    return CakeSpecification(**(design.get("structured_specification") or {}))
