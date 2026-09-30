"""
Chair endpoints (/chair/*) — Frontend-API-Contract.md §5, §6 and §7.

Split across three frontend views (committee overview, paper grading, awards) but kept
in one module because they share the committee scope, the rubric concept, and the
delegate roster. If this file grows past comfortable, split it by resource:
chairs_committee.py / chairs_papers.py / chairs_awards.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from API.dependencies import CurrentUser, get_current_user, require_roles
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


# --- Committee overview (§5) ---


@router.get("/committee/overview", response_model=CommitteeOverviewResponse)
def get_committee_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CommitteeOverviewResponse:
    """
    Return the chair's committee metrics and conference timeline.

    TODO: `timeline` must always carry both `preConference` and `duringConference`,
    even when empty. Timestamps must be ISO-8601 so the frontend can derive each
    event's completed/active/upcoming state.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


# --- Paper grading (§6) ---
# NOTE: this rubric is flat ({id, label, maxScore}). The awards rubric below is a
# different endpoint with a different shape - do not merge them.


@router.get("/rubric", response_model=list[GradingRubricCriterion])
def get_grading_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GradingRubricCriterion]:
    """Return the numeric grading rubric used by the position-paper grading view."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/delegates", response_model=list[GradingDelegate])
def list_committee_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GradingDelegate]:
    """
    Return the committee roster with each delegate's paper status and grading state.

    TODO: `pdfUrl` is bound straight to an <iframe> src by the frontend, which does not
    send the Authorization header. Serve it as a signed/expiring URL, or agree a change
    to the view so it fetches the PDF as a blob instead.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.post("/papers/{delegate_id}/grade")
def grade_position_paper(
    delegate_id: int,
    payload: GradeSubmissionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    """
    Store a delegate's rubric scores and chair comments.

    TODO: note `payload.totalScore` arrives as a pre-formatted string ("18/20") rather
    than a number. Recompute it server-side from `payload.scores` so a client cannot
    submit a score that disagrees with the rubric.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/papers/{delegate_id}/download")
def download_position_paper(
    delegate_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    """
    Return a delegate's position paper as a PDF blob.

    TODO: confirm the delegate is in the chair's committee, then return a Response with
    media_type="application/pdf".
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


# --- Awards (§7) ---
# NOTE: this rubric is nested ({id, label, levels[]}) and is distinct from
# /chair/rubric above.


@router.get("/awards/options", response_model=list[str])
def list_award_options(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str]:
    """
    Return the assignable award names.

    TODO: exclude "None" and "Candidate" — the frontend hardcodes those two options.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/awards/rubric", response_model=list[AwardsRubricCriterion])
def get_awards_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[AwardsRubricCriterion]:
    """Return the leveled rubric used by the awards view."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/awards/delegates", response_model=list[AwardDelegate])
def list_award_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[AwardDelegate]:
    """
    Return the committee roster with each delegate's current award assignments and scores.

    `assignedAward` must be one of the names returned by /chair/awards/options, or "None".
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.post("/awards/{delegate_id}")
def assign_award(
    delegate_id: int,
    payload: AwardAssignmentRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    """
    Assign an award and rubric scores to a delegate.

    TODO: the frontend enforces that official awards require every rubric criterion to be
    scored; re-check that server-side. `payload.totalScore` is a number here.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")
