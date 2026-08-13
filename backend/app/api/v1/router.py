"""API v1 router.

Customer and administrative routes are mounted as separate modules so the
boundary between "anyone with a session link" and "authenticated staff" is
visible in the file layout, not just in a decorator.
"""

from fastapi import APIRouter

from app.api.v1 import admin, catalog, design_sessions, designs, orders, quoting

api_router = APIRouter()

# Customer-facing: reached with a session token, or no credential at all.
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(quoting.router)
api_router.include_router(design_sessions.router)
api_router.include_router(designs.router)
api_router.include_router(orders.router)

# Staff only: every route depends on current_admin.
api_router.include_router(admin.router)
