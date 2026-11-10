"""
Chair endpoints (/chair/*) — Frontend-API-Contract.md §5, §6 and §7.

Transport only: resolve the caller, call one use case from `core.domain.chairs`, map the
result to a response, and translate domain failures with `_http_error`. The committee
scope, the grading rules and the award rules all live in the domain module.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import core.audit
from API.dependencies import CurrentUser, get_current_user, require_roles
from core.domain import chairs as chairs_domain
from core.domain import errors as domain_errors
from crud.db import get_db
from schemas.request_models import AwardAssignmentRequest, GradeSubmissionRequest
from schemas.response_models import (
    AwardDelegate,
    AwardsRubricCriterion,
    CommitteeOverviewResponse,
    GradingDelegate,
    GradingRubricCriterion,
)

# Chair views are also reachable by admins, matching the Vue router's meta.roles.
router = APIRouter(
    prefix="/chair",
    tags=["chair"],
    dependencies=[Depends(require_roles("chair", "admin"))],
)


def _http_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a chair domain failure into the status code and body the contract documents."""
    if isinstance(exc, domain_errors.ChairNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No chair profile is attached to this account.",
        )
    if isinstance(exc, domain_errors.DelegateNotInCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such delegate in your committee.",
        )
    if isinstance(exc, domain_errors.PaperNotSubmitted):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "This delegate has not submitted a position paper yet.",
        )
    if isinstance(exc, domain_errors.PaperFileMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. The paper has to be uploaded again.",
        )
    if isinstance(exc, domain_errors.RubricNotConfigured):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The grading rubric has no criteria configured yet.",
        )
    if isinstance(exc, domain_errors.ScoreCriterionUnknown):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "scores contains criteria that are not in the rubric: "
            + ", ".join(exc.criteria)
            + ".",
        )
    if isinstance(exc, domain_errors.ScoreOutOfRange):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{exc.label} must be between 0 and {exc.maximum}; got {exc.got}.",
        )
    if isinstance(exc, domain_errors.CommentsTooLong):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Comments are limited to {exc.limit} characters.",
        )
    if isinstance(exc, domain_errors.AwardNotAssignable):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"assignedAward must be one of: {', '.join(sorted(exc.allowed))}.",
        )
    if isinstance(exc, domain_errors.AwardCriteriaUnscored):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Every rubric criterion must be scored before assigning {exc.award}. "
            f"Missing: {', '.join(exc.missing)}.",
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


def _download_error(exc: domain_errors.DomainError) -> HTTPException:
    """The download route's view of a domain failure.

    "This delegate has not submitted a paper yet" is a 409 when a chair tries to *grade*
    one, but a plain 404 when they try to *fetch* one - there is simply nothing there. Same
    domain condition, two contract messages, so this specialises the shared mapping instead
    of duplicating it.
    """
    if isinstance(exc, domain_errors.PaperNotSubmitted):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No position paper has been submitted yet.",
        )
    return _http_error(exc)


# --- Committee overview (§5) ---


@router.get("/committee/overview", response_model=CommitteeOverviewResponse)
def get_committee_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeOverviewResponse:
    """
    Return the chair's committee metrics and the conference timeline.

    Counts are scoped to the chair's own committee; the timeline is conference-wide,
    because every committee runs on the same schedule. Each event is a point in time
    rather than a flag - the frontend compares it with the clock, which is why the lists
    come back in ascending time order and why each timestamp carries an explicit UTC
    offset.
    """
    try:
        return chairs_domain.get_committee_overview(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc


# --- Paper grading (§6) ---


@router.get("/rubric", response_model=list[GradingRubricCriterion])
def get_position_paper_grading_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[GradingRubricCriterion]:
    """
    Return the numeric grading rubric used by the position-paper grading view.

    The criteria are conference-wide and admin-editable (PUT /admin/rubrics), so they come
    from the `rubrics` document rather than a constant in the code. The endpoint exists so
    the frontend has one place to read the labels and maxima from; the marks themselves
    are stored per delegate by POST /chair/papers/{id}/grade.
    """
    return chairs_domain.get_position_paper_grading_rubric(db)


@router.get("/delegates", response_model=list[GradingDelegate])
def list_committee_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[GradingDelegate]:
    """
    Return the committee roster with each delegate's paper status and grading state.

    `submissionDate` is the newest upload's time as an ISO-8601 instant carrying a UTC
    offset - the column is naive UTC, and the view localises it for display. It is empty
    for a delegate who has never uploaded.

    There is deliberately no `pdfUrl`: an iframe cannot send the Authorization header, so
    the view fetches /chair/papers/{id}/download as a blob through the API client instead
    and previews that.
    """
    try:
        return chairs_domain.list_committee_delegates(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc


@router.post("/papers/{delegate_id}/grade")
def grade_position_paper(
    delegate_id: int,
    payload: GradeSubmissionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Store a delegate's rubric scores and chair comments, and mark the paper graded.

    The scope, the rubric checks and the recomputed total live in
    `core.domain.chairs.grade_paper`; `delegate_id` comes from the path, and the copy in
    the body is ignored. Re-grading is allowed - a chair correcting a mistake overwrites
    the previous marks.
    """
    try:
        outcome = chairs_domain.grade_paper(
            db,
            user.id,
            delegate_id,
            scores=payload.scores,
            comments=payload.comments,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc

    return {"message": "Grade saved.", "totalScore": outcome.total}


@router.get("/papers/{delegate_id}/download")
def download_position_paper(
    delegate_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Return a delegate's position paper as a PDF blob.

    Scoped to the chair's own committee, so an id from another committee answers 404
    exactly as an unknown one does. The paper served is the newest upload, matching what
    /chair/delegates reports as submitted.
    """
    try:
        paper = chairs_domain.get_paper_file(db, user.id, delegate_id)
    except domain_errors.DomainError as exc:
        raise _download_error(exc) from exc

    return FileResponse(
        paper.path,
        media_type="application/pdf",
        filename=paper.download_name or "position-paper.pdf",
    )


# --- Awards (§7) ---


@router.get("/awards/options", response_model=list[str])
def list_award_options(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str]:
    """
    Return the assignable award names, in the order core.controls lists them.

    Static, like the grading rubric: the same awards are on offer in every committee.
    """
    return chairs_domain.list_award_options()


@router.get("/awards/rubric", response_model=list[AwardsRubricCriterion])
def get_awards_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[AwardsRubricCriterion]:
    """
    Return the leveled rubric used by the awards view.

    Admin-editable (PUT /admin/rubrics), shared by every committee - one score per
    criterion is stored per delegate, chosen from that criterion's levels. Levels keep the
    order they are saved in, which is the order the view renders as score cells.
    """
    return chairs_domain.get_awards_rubric(db)


@router.get("/awards/delegates", response_model=list[AwardDelegate])
def list_award_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[AwardDelegate]:
    """
    Return the committee roster with each delegate's current award assignments and scores.

    `assignedAward` is one of the names from /chair/awards/options, or "None" /
    "Candidate". `totalScore` is null until a chair has saved something for that delegate -
    the view hides the "n pts" badge in that case rather than showing a zero.
    """
    try:
        return chairs_domain.list_award_delegates(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc


@router.post("/awards/{delegate_id}")
def assign_award(
    delegate_id: int,
    payload: AwardAssignmentRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Assign an award and rubric scores to a delegate.

    The committee scope, the allowed award names and the "every criterion must be scored
    before an official award" rule live in `core.domain.chairs.assign_award`. The stored
    total is recomputed from the marks rather than taken from the body.
    """
    try:
        outcome = chairs_domain.assign_award(
            db,
            user.id,
            delegate_id,
            award=payload.assignedAward,
            scores=payload.scores,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc

    return {"message": "Award saved.", "assignedAward": outcome.award}
