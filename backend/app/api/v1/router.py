"""API v1 router.

Customer and administrative routes are mounted as separate modules so the
boundary between "anyone with a session link" and "authenticated staff" is
visible in the file layout, not just in a decorator.
"""

from fastapi import APIRouter

from app.api.v1 import catalog, design_sessions, designs, quoting

api_router = APIRouter()
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(quoting.router)
api_router.include_router(design_sessions.router)
api_router.include_router(designs.router)
