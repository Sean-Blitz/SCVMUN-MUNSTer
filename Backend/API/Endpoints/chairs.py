"""
Chair endpoints (/chair/*) — Frontend-API-Contract.md §5, §6 and §7.

Split across three frontend views (committee overview, paper grading, awards) but kept
in one module because they share the committee scope, the rubric concept, and the
delegate roster. If this file grows past comfortable, split it by resource:
chairs_committee.py / chairs_papers.py / chairs_awards.py.
"""

from typing import Annotated

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
from core.controls import (
    TIMELINE_PHASES,
    award_options,
    awards_rubric,
    paper_rubric_data,
)
from crud.database_schema import Account, Chairs, Delegates, TimelineEvent
from crud.db import get_db
from schemas.request_models import AwardAssignmentRequest, GradeSubmissionRequest
from schemas.response_models import (
    AwardDelegate,
    AwardsRubricCriterion,
    CommitteeOverviewResponse,
    GradingDelegate,
    GradingRubricCriterion,
    RubricLevel,
    Timeline,
    TimelineEvent as TimelineEventModel,
)

# Chair views are also reachable by admins, matching the Vue router's meta.roles.
router = APIRouter(
    prefix="/chair",
    tags=["chair"],
    dependencies=[Depends(require_roles("chair", "admin"))],
)


# --- Committee overview (§5) ---


def _iso_utc(moment) -> str:
    """Render a naive-UTC column value as an ISO-8601 string that says so.

    The database stores naive UTC, but `new Date("2026-10-04T09:00:00")` in a browser
    reads that as *local* time - which would shift every timeline event by the viewer's
    offset and make the completed/active/upcoming derivation wrong. Attaching +00:00
    keeps the instant unambiguous for the client.
    """
    return moment.replace(tzinfo=timezone.utc).isoformat()


@router.get("/committee/overview", response_model=CommitteeOverviewResponse)
def get_committee_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeOverviewResponse:
    """
    Return the chair's committee metrics and the conference timeline.

    Counts are scoped to the chair's own committee; the timeline is conference-wide
    (timeline_events), because every committee runs on the same schedule. Each event is
    a point in time rather than a flag - the frontend compares it with the clock, which
    is why the lists come back in ascending time order and why each timestamp carries an
    explicit UTC offset.
    """
    chair = db.scalars(select(Chairs).where(Chairs.account_id == user.id)).first()
    if chair is None:
        # Admins may reach the chair views; without a chair profile there is no
        # committee to scope the numbers to.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No chair profile is attached to this account.",
        )

    committee = chair.committee_name

    total_delegates = db.scalar(
        select(func.count()).select_from(Delegates).where(Delegates.committee == committee)
    )
    delegates_registered = db.scalar(
        select(func.count())
        .select_from(Delegates)
        .join(Account, Account.id == Delegates.account_id)
        .where(Delegates.committee == committee, Account.password_hash.is_not(None))
    )
    papers_graded = db.scalar(
        select(func.count())
        .select_from(Delegates)
        .where(Delegates.committee == committee, Delegates.paper_status == "graded")
    )
    # "Submitted" means anything a chair can mark, graded papers included: the dashboard
    # renders this as `papersGraded / totalPapersSubmitted`.
    papers_submitted = db.scalar(
        select(func.count())
        .select_from(Delegates)
        .where(
            Delegates.committee == committee,
            Delegates.paper_status.in_(("submitted", "graded")),
        )
    )

    events = db.scalars(
        select(TimelineEvent).order_by(TimelineEvent.starts_at, TimelineEvent.id)
    ).all()

    # Both keys are always present, even when empty - the template iterates them directly.
    timeline = Timeline(
        **{
            phase: [
                TimelineEventModel(label=event.label, timestamp=_iso_utc(event.starts_at))
                for event in events
                if event.phase == phase
            ]
            for phase in TIMELINE_PHASES
        }
    )

    return CommitteeOverviewResponse(
        chairName=chair.name,
        committeeName=committee,
        delegatesRegistered=delegates_registered or 0,
        totalDelegates=total_delegates or 0,
        papersGraded=papers_graded or 0,
        totalPapersSubmitted=papers_submitted or 0,
        timeline=timeline,
    )


# --- Paper grading (§6) ---
# NOTE: this rubric is flat ({id, label, maxScore}). The awards rubric below is a
# different endpoint with a different shape - do not merge them.


@router.get("/rubric", response_model=list[GradingRubricCriterion])
def get_position_paper_grading_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GradingRubricCriterion]:
    """
    Return the numeric grading rubric used by the position-paper grading view.

    A static list from `core.controls.paper_rubric_data`, not a table: the criteria are
    the same for every chair and every delegate, so there is nothing per-committee to
    store and no database session is needed here at all. The endpoint exists so the
    frontend has one place to read the labels and maxima from.

    The same list is the source the delegate's graded breakdown is joined against
    (/delegate/my-assignment), which is what keeps both views showing the same labels and
    the same maximum marks.

    An entry with no `id` is skipped: `id` is the key a mark is stored under, so such an
    entry could never be graded - the delegate-side join skips it for the same reason.
    """
    rubric: list[GradingRubricCriterion] = []
    for criterion in paper_rubric_data:
        criterion_id = criterion.get("id")
        if criterion_id is None:
            continue
        rubric.append(
            GradingRubricCriterion(
                id=criterion_id,
                label=criterion.get("label") or str(criterion_id),
                maxScore=float(criterion.get("maxScore", 0)),
            )
        )
    return rubric


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


# "None" and "Candidate" are the template's own two options (no award / shortlist), so the
# API must never send them back or the dropdown would list them twice. Compared
# case-insensitively and filtered here rather than trusted, so that adding one of them to
# core.controls cannot quietly break the view.
RESERVED_AWARD_OPTIONS = {"none", "candidate"}


@router.get("/awards/options", response_model=list[str])
def list_award_options(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str]:
    """
    Return the assignable award names, in the order core.controls lists them.

    Static, like the grading rubric: the same awards are on offer in every committee.
    """
    return [
        name.strip()
        for name in award_options
        if name.strip() and name.strip().casefold() not in RESERVED_AWARD_OPTIONS
    ]


@router.get("/awards/rubric", response_model=list[AwardsRubricCriterion])
def get_awards_rubric(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[AwardsRubricCriterion]:
    """
    Return the leveled rubric used by the awards view.

    Static and shared, from core.controls.awards_rubric - one score per criterion is
    stored per delegate, chosen from that criterion's levels. Levels keep the order they
    are written in, which is the order the view renders as score cells.

    Nothing here is derived: the view works out each criterion's maximum itself, as the
    highest `level.score`. That is why a criterion with no usable levels is skipped
    entirely - sending one would leave the client taking `Math.max()` of an empty list,
    i.e. -Infinity as its maximum. A level with no label is skipped for the same reason a
    label-less checklist line is: there would be nothing to render in the cell.
    """
    rubric: list[AwardsRubricCriterion] = []

    for criterion in awards_rubric:
        criterion_id = criterion.get("id")
        if criterion_id is None:
            # `id` keys the scores map, so a criterion without one could never be stored.
            continue

        levels: list[RubricLevel] = []
        for level in criterion.get("levels") or []:
            if not isinstance(level, dict):
                continue
            label = str(level.get("label") or "").strip()
            if not label:
                continue
            levels.append(
                RubricLevel(
                    score=float(level.get("score", 0)),
                    label=label,
                    description=str(level.get("description") or ""),
                )
            )

        if not levels:
            continue

        rubric.append(
            AwardsRubricCriterion(
                id=criterion_id,
                label=str(criterion.get("label") or criterion_id),
                levels=levels,
            )
        )

    return rubric


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
