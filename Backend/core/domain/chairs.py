"""Chair use cases: committee overview, paper grading, and awards.

Same three rules as `core.domain.delegates`:

* nothing here imports FastAPI, Starlette or `API.*`;
* it takes the caller's `account_id` and a delegate id, and returns data (a response model
  or a small outcome object) rather than a `Response`;
* failures are `core.domain.errors` exceptions, mapped to status codes by
  `API/Endpoints/chairs.py`.

Audit lines take an `actor: str` (`role:id`) instead of the authenticated-caller model, so
nothing in this module depends on the transport layer. Writing the audit entry is part of
the use case: it happens after the commit, inside the same function that owns the
transaction.

The response models are built here rather than in the endpoints. That is the pragmatic
half of the split - the payloads are shaped exactly like the contract - and moving them to a
presenter later is confined to this file.
"""

from dataclasses import dataclass
from datetime import timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.audit
from core import controls
from core.domain import papers
from core.domain.errors import (
    AwardCriteriaUnscored,
    AwardNotAssignable,
    ChairNotFound,
    CommentsTooLong,
    DelegateNotInCommittee,
    PaperNotSubmitted,
    RubricNotConfigured,
    ScoreCriterionUnknown,
    ScoreOutOfRange,
)
from crud.database_schema import Account, Chairs, Delegates, TimelineEvent, Uploads
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

# The comments column is String(500); a longer comment is refused here rather than left to
# Postgres, which would raise a DataError the endpoint would report as a 500.
MAX_GRADE_COMMENTS = 500

# "None" and "Candidate" are the template's own two options (no award / shortlist), so the
# API must never send them back or the dropdown would list them twice. Compared
# case-insensitively and filtered here rather than trusted, so adding one of them to
# core.controls cannot quietly break the view.
RESERVED_AWARD_OPTIONS = {"none", "candidate"}


@dataclass(frozen=True)
class GradeOutcome:
    """What the grading endpoint needs to build its response."""

    total: str  # "<earned>/<max>", e.g. "18/20"


@dataclass(frozen=True)
class AwardOutcome:
    """What the award endpoint needs to build its response."""

    award: str
    total: float | None


def _chair_for(db: Session, account_id: int) -> Chairs:
    """The caller's chair profile, or a domain error naming what is missing."""
    chair = db.scalars(select(Chairs).where(Chairs.account_id == account_id)).first()
    if chair is None:
        raise ChairNotFound()
    return chair


def _committee_delegate(db: Session, chair: Chairs, delegate_id: int) -> Delegates:
    """A delegate in the chair's own committee, or a domain error.

    An id from another committee fails exactly like an unknown one: a chair has no way to
    tell the two apart, and should not be able to probe other committees by id.
    """
    delegate = db.scalars(
        select(Delegates).where(
            Delegates.account_id == delegate_id,
            Delegates.committee == chair.committee_name,
        )
    ).first()
    if delegate is None:
        raise DelegateNotInCommittee()
    return delegate


def format_mark(value: float) -> str:
    """Render a mark for display: 18.0 -> "18", 8.5 -> "8.5".

    Shared with the endpoints because the same rendering appears in a stored grade
    ("18/20") and in the message for a rejected mark.
    """
    return f"{value:g}"


def _iso_utc(moment) -> str:
    """Render a naive-UTC column value as an ISO-8601 string that says so.

    The database stores naive UTC, but `new Date("2026-10-04T09:00:00")` in a browser
    reads that as *local* time - which would shift every timeline event by the viewer's
    offset and make the completed/active/upcoming derivation wrong. Attaching +00:00
    keeps the instant unambiguous for the client.
    """
    return moment.replace(tzinfo=timezone.utc).isoformat()


def _stored_scores(raw: Any) -> dict[str, float]:
    """Coerce a stored rubric map into {criterion id: mark}.

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


# --- Committee overview ----------------------------------------------------------------


def get_committee_overview(db: Session, account_id: int) -> CommitteeOverviewResponse:
    """The chair's committee metrics plus the conference-wide timeline.

    Counts are scoped to the chair's own committee; the timeline is conference-wide
    (timeline_events), because every committee runs on the same schedule. Each event is a
    point in time rather than a flag - the frontend compares it with the clock, which is
    why the lists come back in ascending time order and why each timestamp carries an
    explicit UTC offset.
    """
    chair = _chair_for(db, account_id)
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
            for phase in controls.TIMELINE_PHASES
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


# --- Paper grading ---------------------------------------------------------------------
# NOTE: this rubric is flat ({id, label, maxScore}). The awards rubric below is a different
# endpoint with a different shape - do not merge them.


def build_paper_rubric() -> list[GradingRubricCriterion]:
    """
    The position-paper grading rubric, built from `core.controls.paper_rubric_data`.

    A static list, not a table: the criteria are the same for every chair and every
    delegate, so there is nothing per-committee to store and no database session is needed
    to read it.

    A function rather than an inline body because `grade_paper` validates marks against
    exactly the criteria this publishes: if the two drifted, a chair could be blocked from
    saving a mark for a criterion the screen had just shown them.

    The same list is the source the delegate's graded breakdown is joined against
    (/delegate/my-assignment), which is what keeps both views showing the same labels and
    the same maximum marks.

    An entry with no `id` is skipped: `id` is the key a mark is stored under, so such an
    entry could never be graded - the delegate-side join skips it for the same reason.
    """
    rubric: list[GradingRubricCriterion] = []
    for criterion in controls.paper_rubric_data:
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


def get_position_paper_grading_rubric() -> list[GradingRubricCriterion]:
    """The numeric rubric the grading view reads its labels and maxima from."""
    return build_paper_rubric()


def list_committee_delegates(db: Session, account_id: int) -> list[GradingDelegate]:
    """
    The committee roster with each delegate's paper status and grading state.

    Two queries, not one per row: the roster, then every paper belonging to those
    delegates newest-first, reduced to the current one per delegate. A committee can hold
    80 delegates, and a query each would be 81 round trips for a page that shows a grid.

    `submissionDate` is the newest upload's time as an ISO-8601 instant carrying a UTC
    offset - the column is naive UTC, and the view localises it for display. It is empty
    for a delegate who has never uploaded.
    """
    chair = _chair_for(db, account_id)

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


def grade_paper(
    db: Session,
    account_id: int,
    delegate_id: int,
    *,
    scores: dict[str, Any],
    comments: str,
    actor: str,
) -> GradeOutcome:
    """
    Store a delegate's rubric scores and comments, and mark the paper graded.

    The stored total is **recomputed** as `<sum of marks>/<sum of rubric maxima>` rather
    than taken from the request, so a client cannot submit a score line that disagrees with
    the rubric. Re-grading is allowed - a chair correcting a mistake overwrites the
    previous marks.

    Every mark has to name a criterion from the rubric the view was given, and sit between
    0 and that criterion's maximum (the input's `max` attribute is only a hint).
    """
    chair = _chair_for(db, account_id)
    delegate = _committee_delegate(db, chair, delegate_id)

    if delegate.paper_status == "unsubmitted":
        raise PaperNotSubmitted()

    rubric = {str(criterion.id): criterion for criterion in build_paper_rubric()}
    if not rubric:
        raise RubricNotConfigured()

    marks: dict[str, float] = {}
    for criterion_id, submitted in scores.items():
        key = str(criterion_id)
        criterion = rubric.get(key)
        if criterion is None:
            raise ScoreCriterionUnknown((key,))

        mark = float(submitted)
        # A hair of tolerance, so a mark that equals the maximum is never rejected by
        # floating-point representation.
        if mark < 0 or mark > criterion.maxScore + 1e-9:
            raise ScoreOutOfRange(
                criterion.label,
                format_mark(criterion.maxScore),
                format_mark(mark),
            )
        marks[key] = mark

    trimmed = comments.strip()
    if len(trimmed) > MAX_GRADE_COMMENTS:
        raise CommentsTooLong(MAX_GRADE_COMMENTS)

    already_graded = delegate.paper_status == "graded"
    earned = sum(marks.values())
    possible = sum(criterion.maxScore for criterion in rubric.values())

    delegate.paper_rubric_grade = marks
    delegate.paper_comments = trimmed or None
    delegate.paper_grade = f"{format_mark(earned)}/{format_mark(possible)}"
    delegate.paper_status = "graded"
    db.commit()

    core.audit.business(
        "grade.saved",
        actor=actor,
        delegate=delegate.account_id,
        country=delegate.country,
        committee=delegate.committee,
        total=delegate.paper_grade,
        criteria=len(marks),
        regrade=already_graded,
    )

    return GradeOutcome(total=delegate.paper_grade)


def get_paper_file(db: Session, account_id: int, delegate_id: int) -> papers.PaperFile:
    """A delegate's paper, scoped to the chair's committee and resolved to bytes.

    The file is located from the database row rather than from anything the client sends.
    """
    chair = _chair_for(db, account_id)
    delegate = _committee_delegate(db, chair, delegate_id)

    paper = papers.paper_in_force(db, delegate.account_id)
    return papers.PaperFile(
        path=paper.path,
        download_name=f"{delegate.country}_Position_Paper.pdf",
    )


# --- Awards ----------------------------------------------------------------------------
# NOTE: this rubric is nested ({id, label, levels[]}) and is distinct from the paper rubric.


def assignable_awards() -> list[str]:
    """The award names a chair may hand out, in the order core.controls lists them."""
    return [
        name.strip()
        for name in controls.award_options
        if name.strip() and name.strip().casefold() not in RESERVED_AWARD_OPTIONS
    ]


def list_award_options() -> list[str]:
    """The assignable award names, in the order core.controls lists them."""
    return assignable_awards()


def build_awards_rubric() -> list[AwardsRubricCriterion]:
    """
    The awards rubric, built from core.controls.awards_rubric.

    Kept as a function rather than inlined because `assign_award` validates incoming marks
    against exactly the criteria this publishes - if the two ever drifted, a chair could be
    blocked from saving an award the screen had just asked them to score.

    A criterion with no usable levels is skipped entirely: the view works out each
    criterion's maximum as `Math.max(...levels)`, so an empty list would give it -Infinity.
    A level with no label is skipped for the same reason a label-less checklist line is:
    there would be nothing to render.
    """
    rubric: list[AwardsRubricCriterion] = []

    for criterion in controls.awards_rubric:
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


def get_awards_rubric() -> list[AwardsRubricCriterion]:
    """The leveled rubric used by the awards view."""
    return build_awards_rubric()


def list_award_delegates(db: Session, account_id: int) -> list[AwardDelegate]:
    """
    The committee roster with each delegate's award assignment and scores.

    `assignedAward` is one of the names from /chair/awards/options, or "None" /
    "Candidate". `totalScore` is null until a chair has saved something for that delegate -
    the view hides the "n pts" badge in that case rather than showing a zero.
    """
    chair = _chair_for(db, account_id)

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


def assign_award(
    db: Session,
    account_id: int,
    delegate_id: int,
    *,
    award: str,
    scores: dict[str, Any],
    actor: str,
) -> AwardOutcome:
    """
    Assign an award and rubric scores to a delegate in the chair's committee.

    The frontend already refuses to give an official award until every rubric criterion has
    been scored; the same rule is enforced here, because a script would otherwise be able to
    store an award that was never evaluated. Marks are also checked against the rubric the
    view was given, so a stale criterion id cannot be parked in the database.

    The stored total is **recomputed** as the sum of the marks rather than taken from the
    request: the total is a derived value, and a client that disagreed would put a wrong
    number in front of the chair.
    """
    chair = _chair_for(db, account_id)
    delegate = _committee_delegate(db, chair, delegate_id)

    chosen = award.strip()
    # "None" (no award) and "Candidate" (shortlist) are the template's own two options and
    # are legitimately assignable, even though they are not in /chair/awards/options.
    allowed_names = ("Candidate", "None", *assignable_awards())
    if chosen not in allowed_names:
        raise AwardNotAssignable(allowed_names)

    marks = {str(criterion_id): float(mark) for criterion_id, mark in scores.items()}

    rubric = build_awards_rubric()
    labels = {str(criterion.id): criterion.label for criterion in rubric}

    unknown = sorted(set(marks) - set(labels))
    if unknown:
        raise ScoreCriterionUnknown(tuple(unknown))

    if chosen not in ("None", "Candidate"):
        missing = tuple(
            labels[criterion_id] for criterion_id in labels if criterion_id not in marks
        )
        if missing:
            raise AwardCriteriaUnscored(chosen, missing)

    delegate.assigned_award = chosen
    delegate.overall_rubric_scores = marks
    # NULL rather than 0.0 when nothing was scored, so the badge stays hidden.
    delegate.overall_total_score = sum(marks.values()) if marks else None
    db.commit()

    core.audit.business(
        "award.assigned",
        actor=actor,
        delegate=delegate.account_id,
        country=delegate.country,
        committee=delegate.committee,
        award=chosen,
        total=delegate.overall_total_score,
        criteria=len(marks),
    )

    return AwardOutcome(award=chosen, total=delegate.overall_total_score)
