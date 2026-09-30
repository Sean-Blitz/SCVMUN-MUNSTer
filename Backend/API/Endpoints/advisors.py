"""
Advisor endpoints (/advisor/*) — Frontend-API-Contract.md §3 and §4.

An advisor is scoped to one school, so every route resolves the school from the
calling user rather than accepting a school identifier from the client.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from API.dependencies import CurrentUser, get_current_user, require_roles
from schemas.request_models import VerifyHashesRequest
from schemas.response_models import AdvisorDelegatesResponse, AdvisorSchoolResponse

router = APIRouter(
    prefix="/advisor",
    tags=["advisor"],
    dependencies=[Depends(require_roles("advisor"))],
)


@router.get("/delegates", response_model=AdvisorDelegatesResponse)
def list_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdvisorDelegatesResponse:
    """
    List the advisor's delegates. `hash` must be masked here — the real values are only
    released by /advisor/verify-hashes.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/delegates/{delegate_id}/paper")
def download_delegate_paper(
    delegate_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    """
    Return the delegate's position paper as a PDF blob.

    TODO: verify `delegate_id` belongs to the advisor's school before serving the file,
    and return a Response with media_type="application/pdf".
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.post("/verify-hashes", response_model=AdvisorDelegatesResponse)
def verify_hashes_and_reveal(
    payload: VerifyHashesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdvisorDelegatesResponse:
    """
    Re-authenticate the advisor and, on success, return the same delegate list with real
    (unmasked) hashes.

    TODO: compare `payload.password` against the caller's credentials. On mismatch raise
    401 with a message — the frontend displays it inside the password modal.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/school", response_model=AdvisorSchoolResponse)
def get_school_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdvisorSchoolResponse:
    """Return the advisor's school details, billing status, and conference checklist."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")
