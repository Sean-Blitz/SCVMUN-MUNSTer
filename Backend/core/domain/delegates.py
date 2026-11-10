"""Delegate use cases: the dashboard payload, their paper download, and a paper submission.

Rules this module follows, so the endpoints stay transport-only:

* nothing here imports FastAPI, Starlette or `API.*` - the domain does not know it is
  served over HTTP;
* it takes an `account_id`, not the authenticated-caller model, and returns data (a
  response model or a small result object) rather than a `Response`;
* failures are `core.domain.errors` exceptions; `API/Endpoints/delegates.py` maps them to
  status codes. `get_delegate_dashboard` still returns `None` for "no profile", which has
  exactly one HTTP mapping and carries no data to hand back.

The database session is always passed in and never created here, so a test can hand in a
session of its own and a future unit of work can wrap several calls in one transaction.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import core.audit
import core.storage
from core import controls
from core.domain import papers, rubrics
from core.domain.errors import (
    DelegateNotFound,
    NotAPdf,
    PaperAlreadyGraded,
    PaperStorageFailed,
    PaperTooLarge,
    UploadRateLimited,
)
from crud.database_schema import Broadcast, Delegates, Uploads
from crud.db import utcnow
from schemas.response_models import (
    ConferenceLink,
    DelegateAssignmentResponse,
    DelegateInfo,
    GradedCriterion,
    PositionPaper,
)

# How far back the upload cap looks, and how long the endpoint tells the client to wait.
UPLOAD_WINDOW_HOURS = 1


@dataclass(frozen=True)
class UploadResult:
    """What the upload endpoint needs to build its response."""

    file_name: str
    status: str


def _visible_broadcasts(db: Session, kind: str, committee: str) -> list[Broadcast]:
    """The broadcasts of one kind this delegate should see, in display order.

    A row addressed to no committee (`committee_name IS NULL`) goes to everyone;
    otherwise it goes only to the delegates whose own committee matches. Rows whose
    schedule window does not cover "now" are left out.

    Ordering is global lines first, then the delegate's own committee, each in
    `position` order - positions only compete within one target, so a committee line
    can never land between two general ones. `id` breaks ties.

    The admin-side caps (core.controls.BROADCAST_LIMITS) are what guarantee this never
    returns more lines than the dashboard can render - 3 announcements, 5 links.
    """
    now = utcnow()
    stmt = (
        select(Broadcast)
        .where(
            Broadcast.kind == kind,
            or_(Broadcast.committee_name.is_(None), Broadcast.committee_name == committee),
            or_(Broadcast.starts_at.is_(None), Broadcast.starts_at <= now),
            or_(Broadcast.ends_at.is_(None), Broadcast.ends_at > now),
        )
        .order_by(
            Broadcast.committee_name.is_(None).desc(),  # general lines first
            Broadcast.position,
            Broadcast.id,
        )
    )
    return list(db.scalars(stmt).all())


def _paper_criteria(db: Session, delegate: Delegates) -> list[GradedCriterion]:
    """Join the chair's stored marks with the rubric, for the grade breakdown.

    `paper_rubric_grade` holds the chair's {criterion id: score} map; the labels and
    maxima come from the rubric itself (core.domain.rubrics). The delegate cannot call
    /chair/rubric - it is role-gated - so the labels have to be resolved here. A
    criterion the chair left unmarked is skipped rather than reported as a zero.

    The lookup compares ids *as strings*: JSONB keys are always strings, so a rubric whose
    ids are numbers (which GradingRubricCriterion allows) would otherwise never match its
    own stored marks and silently vanish from the breakdown.

    Reading the criteria through the same module the grading view uses is what stops a
    rubric the admin edited from rendering differently on the two sides.
    """
    scores = {str(key): value for key, value in (delegate.paper_rubric_grade or {}).items()}

    criteria: list[GradedCriterion] = []
    for criterion in rubrics.paper_criteria(db):
        key = str(criterion.id)
        if key not in scores:
            continue
        criteria.append(
            GradedCriterion(
                id=criterion.id,
                label=criterion.label,
                score=float(scores[key]),
                maxScore=float(criterion.maxScore),
            )
        )
    return criteria


def _delegate_for(db: Session, account_id: int) -> Delegates | None:
    return db.scalars(select(Delegates).where(Delegates.account_id == account_id)).first()


def get_delegate_dashboard(
    db: Session, account_id: int
) -> DelegateAssignmentResponse | None:
    """Everything the delegate dashboard renders, or None when the account has no profile."""
    delegate = _delegate_for(db, account_id)
    if delegate is None:
        return None

    announcements = _visible_broadcasts(db, "announcement", delegate.committee)
    links = _visible_broadcasts(db, "link", delegate.committee)

    return DelegateAssignmentResponse(
        announcements=[broadcast.body for broadcast in announcements],
        delegate=DelegateInfo(committee=delegate.committee, country=delegate.country),
        conferenceLinks=[
            ConferenceLink(text=broadcast.body, url=broadcast.url or "") for broadcast in links
        ],
        positionPaper=PositionPaper(
            status=delegate.paper_status,
            score=delegate.paper_grade or "",
            feedback=delegate.paper_comments or "",
            instructions=[],  # no source for these yet; the panel hides when empty
            criteria=_paper_criteria(db, delegate) if delegate.paper_status == "graded" else [],
        ),
    )


def get_delegate_paper_file(db: Session, account_id: int) -> papers.PaperFile:
    """The caller's own paper, resolved to a file the endpoint can stream.

    The download name is country-based so a chair's inbox is readable. It is only a
    fallback for a direct API call - the view saves the blob under a name of its own.
    """
    delegate = _delegate_for(db, account_id)
    if delegate is None:
        raise DelegateNotFound()

    paper = papers.paper_in_force(db, delegate.account_id)
    return papers.PaperFile(
        path=paper.path,
        download_name=f"{delegate.country}_Position_Paper.pdf",
    )


def submit_paper(
    db: Session,
    account_id: int,
    *,
    file_name: str,
    data: bytes,
    actor: str,
) -> UploadResult:
    """Store one submission, mark the delegate as submitted, and report back.

    `data` is the already-read body: reading the multipart part is transport work, and the
    caller wraps this call in `run_in_threadpool` so the write does not block the event loop.
    `actor` is the audit label (`role:id`), passed as a string so this module never needs the
    authenticated-caller model.

    Two things bound what an upload can cost, because a valid delegate token is otherwise
    free to fill the disk: at most `MAX_UPLOADS_PER_HOUR` submissions in the rolling window,
    and every earlier file for the delegate is deleted once the new one is committed. The
    rows stay as history; only the live paper's bytes exist.
    """
    delegate = _delegate_for(db, account_id)
    if delegate is None:
        raise DelegateNotFound()

    if delegate.paper_status == "graded":
        raise PaperAlreadyGraded()

    # A rolling window read from stored rows. `upload_time` is written explicitly below so
    # this comparison is against the same clock as utcnow(): the column's server default
    # would use the database session's clock and timezone, which need not be UTC.
    window_start = utcnow() - timedelta(hours=UPLOAD_WINDOW_HOURS)
    recent_uploads = db.scalar(
        select(func.count())
        .select_from(Uploads)
        .where(
            Uploads.delegate_id == delegate.account_id,
            Uploads.upload_time >= window_start,
        )
    ) or 0
    if recent_uploads >= controls.MAX_UPLOADS_PER_HOUR:
        raise UploadRateLimited(controls.MAX_UPLOADS_PER_HOUR, UPLOAD_WINDOW_HOURS)

    limit_mb = core.storage.MAX_PAPER_BYTES // (1024 * 1024)
    if len(data) > core.storage.MAX_PAPER_BYTES:
        raise PaperTooLarge(limit_mb)

    # The extension and content type are the client's claims, checked by the endpoint; the
    # %PDF- signature is the check that actually matters.
    if not data.startswith(b"%PDF-"):
        raise NotAPdf()

    stored_name = core.storage.new_paper_name(delegate.account_id)
    try:
        core.storage.save_paper(stored_name, data)
    except OSError as exc:
        raise PaperStorageFailed() from exc

    safe_name = Path(file_name).name[:256] or "position-paper.pdf"
    db.add(
        Uploads(
            delegate_id=delegate.account_id,
            file_name=safe_name,
            file_path=stored_name,  # relative to PAPER_UPLOAD_DIR, never absolute
            upload_time=utcnow(),
        )
    )
    delegate.paper_status = "submitted"

    try:
        db.commit()
    except Exception:
        # The row never landed, so the file on disk would be an orphan: remove it.
        db.rollback()
        core.storage.delete_paper(stored_name)
        raise

    # Committed, so the new paper is safe and the earlier bytes can go. The rows are re-read
    # *after* the commit so two overlapping uploads converge on the same survivor; best
    # effort, because a delete failure must not fail an upload that has already succeeded.
    try:
        replaced = papers.prune_superseded_files(db, delegate.account_id)
    except Exception:
        replaced = 0

    core.audit.business(
        "paper.submitted",
        actor=actor,
        delegate=delegate.account_id,
        country=delegate.country,
        committee=delegate.committee,
        file=stored_name,
        bytes=len(data),
        replaced=replaced,
    )

    return UploadResult(file_name=safe_name, status=delegate.paper_status)
