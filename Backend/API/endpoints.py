"""
Router aggregation for the SCVMUN Platform API.

Each module under Endpoints/ owns one URL namespace (/auth, /delegate, /advisor,
/chair, /admin). They are collected here so main.py only has to import one object,
and so the full route surface can be read in one place.

administrator.py is deliberately not included: it is the legacy CLI-facing app and
creates its own FastAPI instance.
"""

from fastapi import APIRouter

from API.Endpoints import admin, advisors, authorization, chairs, delegates

api_router = APIRouter()

api_router.include_router(authorization.router)
api_router.include_router(delegates.router)
api_router.include_router(advisors.router)
api_router.include_router(chairs.router)
api_router.include_router(admin.router)
