"""
Chair endpoints (/chair/*) — Frontend-API-Contract.md §5, §6 and §7.

Split across three frontend views (committee overview, paper grading, awards) but kept
in one module because they share the committee scope, the rubric concept, and the
delegate roster. If this file grows past comfortable, split it by resource:
chairs_committee.py / chairs_papers.py / chairs_awards.py.
"""

from typing import Annotated, Any

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
from API import papers
from core.controls import (
    TIMELINE_PHASES,
    award_options,
    awards_rubric,
    paper_rubric_data,
)
from crud.database_schema import Account, Chairs, Delegates, TimelineEvent, Uploads
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


def _get_chair(db: Session, account_id: int) -> Chairs:
    """The chair's own profile, or a 404 naming what is missing.

    Admins can reach these routes (the router allows the role) but have no Chairs row, and
    without one there is no committee to scope a roster or an award to.
    """
    chair = db.scalars(select(Chairs).where(Chairs.account_id == account_id)).first()
    if chair is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No chair profile is attached to this account.",
        )
    return chair


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
    chair = _get_chair(db, user.id)
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
    db: Session = Depends(get_db),
) -> list[GradingDelegate]:
    """
    Return the committee roster with each delegate's paper status and grading state.

    Two queries, not one per row: the roster, then every paper belonging to those
    delegates newest-first, reduced to the current one per delegate. A committee can hold
    80 delegates, and a query each would be 81 round trips for a page that shows a grid.

    `submissionDate` is the newest upload's time as an ISO-8601 instant carrying a UTC
    offset - the column is naive UTC, and the view localises it for display. It is empty
    for a delegate who has never uploaded.

    There is deliberately no `pdfUrl`: an iframe cannot send the Authorization header, so
    the view fetches /chair/papers/{id}/download as a blob through the API client instead
    and previews that.
    """
    chair = _get_chair(db, user.id)

    delegates = db.scalars(
        select(Delegates)
        .where(Delegates.committee == chair.committee_name)
        .order_by(Delegates.country)
    ).all()
    if not delegates:
        return []

    uploads = db.scalars(
        select(Uploads)
        .where(Uploads.delegate_id.in_([delegate.account_id for delegate in delegates]))
        .order_by(
            Uploads.delegate_id,
            Uploads.upload_time.desc(),
            Uploads.upload_id.desc(),
        )
    ).all()

    # Uploads are append-only, so the first row seen per delegate is the paper in force.
    newest: dict[int, Uploads] = {}
    for upload in uploads:
        newest.setdefault(upload.delegate_id, upload)

    return [
        GradingDelegate(
            id=delegate.account_id,
            country=delegate.country,
            committee=delegate.committee,
            status=delegate.paper_status,
            submissionDate=(
                _iso_utc(newest[delegate.account_id].upload_time)
                if delegate.account_id in newest
                else ""
            ),
            totalScore=delegate.paper_grade or "",
            scores=_stored_scores(delegate.paper_rubric_grade),
            comments=delegate.paper_comments or "",
        )
        for delegate in delegates
    ]


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
    db: Session = Depends(get_db),
) -> Response:
    """
    Return a delegate's position paper as a PDF blob.

    Scoped to the chair's own committee, so an id from another committee answers 404
    exactly as an unknown one does. The paper served is the newest upload, matching what
    /chair/delegates reports as submitted, and the file is located from the database row
    rather than from anything the client sends.
    """
    chair = _get_chair(db, user.id)

    delegate = db.scalars(
        select(Delegates).where(
            Delegates.account_id == delegate_id,
            Delegates.committee == chair.committee_name,
        )
    ).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such delegate in your committee.",
        )

    # The frontend saves the blob under its own name; this is the fallback for a direct
    # API call.
    return papers.paper_response(
        db,
        delegate.account_id,
        download_name=f"{delegate.country}_Position_Paper.pdf",
    )


# --- Awards (§7) ---
# NOTE: this rubric is nested ({id, label, levels[]}) and is distinct from
# /chair/rubric above.


# "None" and "Candidate" are the template's own two options (no award / shortlist), so the
# API must never send them back or the dropdown would list them twice. Compared
# case-insensitively and filtered here rather than trusted, so that adding one of them to
# core.controls cannot quietly break the view.
RESERVED_AWARD_OPTIONS = {"none", "candidate"}


def _assignable_awards() -> list[str]:
    """The award names a chair may hand out, in the order core.controls lists them."""
    return [
        name.strip()
        for name in award_options
        if name.strip() and name.strip().casefold() not in RESERVED_AWARD_OPTIONS
    ]


@router.get("/awards/options", response_model=list[str])
def list_award_options(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str]:
    """
    Return the assignable award names, in the order core.controls lists them.

    Static, like the grading rubric: the same awards are on offer in every committee.
    """
    return _assignable_awards()


def _build_awards_rubric() -> list[AwardsRubricCriterion]:
    """
    The awards rubric, built from core.controls.awards_rubric.

    Kept as a function rather than inlined in the endpoint because assign_award validates
    incoming marks against exactly the criteria this publishes - if the two ever drifted,
    a chair could be blocked from saving an award the screen had just asked them to score.
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
    return _build_awards_rubric()


def _stored_scores(raw: Any) -> dict[str, float]:
    """Coerce a stored `overall_rubric_scores` map into {criterion id: mark}.

    The column is JSONB, so it could hold anything if it were ever edited by hand; a value
    that is not a number is dropped rather than failing the whole roster.
    """
    if not isinstance(raw, dict):
        return {}

    scores: dict[str, float] = {}
    for criterion_id, mark in raw.items():
        try:
            scores[str(criterion_id)] = float(mark)
        except (TypeError, ValueError):
            continue
    return scores


@router.get("/awards/delegates", response_model=list[AwardDelegate])
def list_award_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[AwardDelegate]:
    """
    Return the committee roster with each delegate's current award assignments and scores.

    `assignedAward` is one of the names returned by /chair/awards/options, or "None" /
    "Candidate". `scores` is the stored {criterion id: mark} map, and `totalScore` is null
    until a chair has saved something for that delegate - the view hides the "n pts" badge
    in that case rather than showing a zero.
    """
    chair = _get_chair(db, user.id)

    delegates = db.scalars(
        select(Delegates)
        .where(Delegates.committee == chair.committee_name)
        .order_by(Delegates.country)
    ).all()

    return [
        AwardDelegate(
            id=delegate.account_id,
            country=delegate.country,
            committee=delegate.committee,
            assignedAward=delegate.assigned_award or "None",
            scores=_stored_scores(delegate.overall_rubric_scores),
            totalScore=(
                float(delegate.overall_total_score)
                if delegate.overall_total_score is not None
                else None
            ),
        )
        for delegate in delegates
    ]


@router.post("/awards/{delegate_id}")
def assign_award(
    delegate_id: int,
    payload: AwardAssignmentRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Assign an award and rubric scores to a delegate.

    The delegate is looked up within the chair's own committee, so an id from another
    committee answers 404 rather than being written to. `delegate_id` comes from the path;
    the copy in the body is ignored.

    The frontend already refuses to give an official award until every rubric criterion has
    been scored; the same rule is enforced here, because a script would otherwise be able
    to store an award that was never evaluated. Marks are also checked against the rubric
    the view was given, so a stale criterion id cannot be parked in the database.

    The stored total is **recomputed** as the sum of the marks rather than taken from
    `payload.totalScore`: the total is a derived value (the view computes it the same way),
    and a client that disagreed would put a wrong number in front of the chair.
    """
    chair = _get_chair(db, user.id)

    delegate = db.scalars(
        select(Delegates).where(
            Delegates.account_id == delegate_id,
            Delegates.committee == chair.committee_name,
        )
    ).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such delegate in your committee.",
        )

    award = payload.assignedAward.strip()
    # "None" (no award) and "Candidate" (shortlist) are the template's own two options and
    # are legitimately assignable, even though they are not in /chair/awards/options.
    allowed = {"None", "Candidate", *_assignable_awards()}
    if award not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"assignedAward must be one of: {', '.join(sorted(allowed))}.",
        )

    scores = {str(criterion_id): float(mark) for criterion_id, mark in payload.scores.items()}

    rubric = _build_awards_rubric()
    labels = {str(criterion.id): criterion.label for criterion in rubric}

    unknown = sorted(set(scores) - set(labels))
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"scores contains criteria that are not in the rubric: {', '.join(unknown)}.",
        )

    if award not in ("None", "Candidate"):
        missing = [labels[criterion_id] for criterion_id in labels if criterion_id not in scores]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Every rubric criterion must be scored before assigning {award}. "
                f"Missing: {', '.join(missing)}.",
            )

    delegate.assigned_award = award
    delegate.overall_rubric_scores = scores
    # NULL rather than 0.0 when nothing was scored, so the badge stays hidden.
    delegate.overall_total_score = sum(scores.values()) if scores else None
    db.commit()

    return {"message": "Award saved.", "assignedAward": award}
