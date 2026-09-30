"""
Admin endpoints (/admin/*) — Frontend-API-Contract.md §8.

Separate from administrator.py on purpose: that module is the legacy CLI-facing app
(its own FastAPI instance, /hashes and /awards), while these routes belong to the
platform API. Keeping them apart means neither has to change for the other.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from API.dependencies import CurrentUser, get_current_user, require_roles
from schemas.response_models import AdminDashboardStatsResponse, PortHealth

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.get("/dashboard-stats", response_model=AdminDashboardStatsResponse)
def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminDashboardStatsResponse:
    """
    Return delegate distribution, server storage usage, and the past week's downtime.

    TODO: `startTime`, `endTime` and `duration` are pre-formatted display strings — the
    frontend renders them verbatim. An empty `downtimeEvents` list is meaningful: it
    renders the "100% Uptime" message.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/ports/health", response_model=list[PortHealth])
def check_port_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PortHealth]:
    """
    Probe the configured service ports and report whether each is reachable.

    TODO: `status` must be exactly "healthy" or "unreachable" — any other value renders
    as unreachable in the UI. Ports must be unique, as they are the list key.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/logs/business.txt")
def download_business_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """
    Return the business log as a plain-text blob.

    TODO: return Response(content=..., media_type="text/plain"). Errors must not be
    returned as JSON here — the frontend saves whatever bytes come back as the .txt file.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/logs/technology.txt")
def download_technology_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """Return the technology log as a plain-text blob. See the note on the business log."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/export/database.csv")
def export_database_csv(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """
    Return a CSV export of the database.

    TODO: return Response(content=..., media_type="text/csv"), ideally with a
    Content-Disposition header.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")
