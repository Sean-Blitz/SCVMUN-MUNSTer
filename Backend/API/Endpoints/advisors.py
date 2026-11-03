"""
Advisor endpoints (/advisor/*) — Frontend-API-Contract.md §3 and §4.

Transport only: resolve the caller, call one use case from `core.domain.advisors`, map the
result, and translate domain failures with `_http_error`. The school scoping rule - every
route resolves the school from the token, never from the client - lives in the domain.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import core.audit
from API.dependencies import CurrentUser, get_current_user, require_roles
from core.domain import advisors as advisors_domain
from core.domain import errors as domain_errors
from crud.db import get_db
from schemas.request_models import VerifyHashesRequest
from schemas.response_models import AdvisorDelegatesResponse, AdvisorSchoolResponse

router = APIRouter(
    prefix="/advisor",
    tags=["advisor"],
    dependencies=[Depends(require_roles("advisor"))],
)


def _http_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate an advisor domain failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.AccountMissing):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    if isinstance(exc, domain_errors.SchoolNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No school is attached to this account.",
        )
    if isinstance(exc, domain_errors.DelegateNotInSchool):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such delegate in your school.",
        )
    if isinstance(exc, domain_errors.PasswordRejected):
        # 403, not 401: the axios interceptor logs the user out on any 401, so a wrong
        # password here would bounce them to the login page instead of showing the message
        # inside the password modal. They are still signed in; they just did not re-prove it.
        return HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Incorrect password. Access denied.",
        )
    if isinstance(exc, domain_errors.PaperFileMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. The paper has to be uploaded again.",
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


def _download_error(exc: domain_errors.DomainError) -> HTTPException:
    """The download route's view of a domain failure.

    Nothing submitted yet is a plain 404 here - there is simply nothing to fetch.
    """
    if isinstance(exc, domain_errors.PaperNotSubmitted):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No position paper has been submitted yet.",
        )
    return _http_error(exc)


@router.get("/delegates", response_model=AdvisorDelegatesResponse)
def list_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorDelegatesResponse:
    """
    List the advisor's delegates, resolved from the caller rather than from a query
    parameter, so one school cannot read another's roster.

    `hash` must be masked here — the real values are only released by
    /advisor/verify-hashes, which asks for the password again first.
    """
    try:
        return advisors_domain.list_delegates(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc


@router.get("/delegates/{delegate_id}/paper")
def download_delegate_paper(
    delegate_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Return the delegate's position paper as a PDF blob.

    `delegate_id` is looked up *within the advisor's own school*, so asking for another
    school's delegate answers 404 exactly as a non-existent one does - there is no
    "exists but forbidden" signal to probe with.
    """
    try:
        paper = advisors_domain.get_paper_file(db, user.id, delegate_id)
    except domain_errors.DomainError as exc:
        raise _download_error(exc) from exc

    return FileResponse(
        paper.path,
        media_type="application/pdf",
        filename=paper.download_name or "position-paper.pdf",
    )


@router.post("/verify-hashes", response_model=AdvisorDelegatesResponse)
def verify_hashes_and_reveal(
    payload: VerifyHashesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorDelegatesResponse:
    """
    Re-authenticate the advisor and, on success, return the same delegate list with real
    (unmasked) hashes.

    A wrong password answers **403, not 401**: the frontend's axios interceptor treats
    every 401 as a dead session and would log the advisor out and redirect to the login
    page instead of showing the message inside the password modal. 401 is kept for the
    case where the token itself resolves to an account that no longer exists, where
    being sent back to the login page is the right outcome.
    """
    try:
        return advisors_domain.reveal_hashes(
            db,
            user.id,
            password=payload.password or "",
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc


@router.get("/school", response_model=AdvisorSchoolResponse)
def get_school_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorSchoolResponse:
    """
    Return the advisor's school details, billing status, and conference checklist.

    Field names follow the frontend's §4.1 shape, which is why several are renames of the
    columns (`school_name` → `name`, `zip_code` → `zip`, `invoiceURL` → `invoiceUrl`).
    """
    try:
        return advisors_domain.get_school_overview(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc
