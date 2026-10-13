"""
Delegate endpoints (/delegate/*) — Frontend-API-Contract.md §2.

Every route here is scoped to the calling delegate; the account comes from the token
rather than from the request body, so a delegate cannot request another's assignment.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
import core.storage
from core.controls import paper_rubric_data
from crud.database_schema import Broadcast, Delegates, Uploads
from crud.db import get_db, utcnow
from schemas.response_models import (
    ConferenceLink,
    DelegateAssignmentResponse,
    DelegateInfo,
    GradedCriterion,
    PositionPaper,
)

router = APIRouter(
    prefix="/delegate",
    tags=["delegate"],
    dependencies=[Depends(require_roles("delegate"))],
)


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
    stmt = (
        select(Broadcast)
        .where(
            Broadcast.kind == kind,
            or_(Broadcast.committee_name.is_(None), Broadcast.committee_name == committee),
            or_(Broadcast.starts_at.is_(None), Broadcast.starts_at <= utcnow()),
            or_(Broadcast.ends_at.is_(None), Broadcast.ends_at > utcnow()),
        )
        .order_by(
            Broadcast.committee_name.is_(None).desc(),  # general lines first
            Broadcast.position,
            Broadcast.id,
        )
    )
    return list(db.scalars(stmt).all())


def _paper_criteria(delegate: Delegates) -> list[GradedCriterion]:
    """Join the chair's stored marks with the rubric, for the grade breakdown.

    `paper_rubric_grade` holds the chair's {criterion id: score} map; the labels and
    maxima come from the rubric itself (core.controls). The delegate cannot call
    /chair/rubric - it is role-gated - so the labels have to be resolved here. A
    criterion the chair left unmarked is skipped rather than reported as a zero.
    """
    scores = delegate.paper_rubric_grade or {}

    criteria: list[GradedCriterion] = []
    for criterion in paper_rubric_data:
        criterion_id = criterion.get("id")
        if criterion_id not in scores:
            continue
        criteria.append(
            GradedCriterion(
                id=criterion_id,
                label=criterion.get("label", str(criterion_id)),
                score=float(scores[criterion_id]),
                maxScore=float(criterion.get("maxScore", 0)),
            )
        )
    return criteria


@router.get("/my-assignment", response_model=DelegateAssignmentResponse)
def get_my_assignment(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> DelegateAssignmentResponse:
    """
    Return everything the delegate dashboard renders: announcements, their committee
    and country, the conference links, and the position-paper panel state including the
    chair's grade and feedback.

    The paper's `criteria` are only filled in once the paper is graded; while it is
    unsubmitted or waiting, the panel shows a waiting message and the list stays empty.
    """
    delegate = db.scalars(select(Delegates).where(Delegates.account_id == user.id)).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No delegate profile is attached to this account.",
        )

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
            criteria=_paper_criteria(delegate) if delegate.paper_status == "graded" else [],
        ),
    )


@router.post("/upload-paper", status_code=status.HTTP_201_CREATED)
async def upload_position_paper(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    paper: Annotated[UploadFile, File(description="Position paper PDF")],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Accept the delegate's position paper as multipart/form-data under the field name
    `paper`, store the PDF on the server, and mark the submission as received.

    Uploading again is allowed until a chair has graded the paper; each attempt is kept
    as its own `position_papers` row (the schema's design), so the newest `upload_time`
    and `upload_id` is the live paper. Once the paper is graded it can no longer be
    replaced.

    The PDF itself lives on disk under PAPER_UPLOAD_DIR (see core.storage); only the
    relative path is recorded. Nothing is served straight from that directory - the
    advisor and chair download routes are what check permissions and stream it.
    """
    delegate = db.scalars(select(Delegates).where(Delegates.account_id == user.id)).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No delegate profile is attached to this account.",
        )

    if delegate.paper_status == "graded":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This paper has already been graded and cannot be replaced.",
        )

    # The extension and content type are the client's claims - cheap to check, trivial to
    # fake - so the %PDF- signature below is the check that actually matters.
    filename = Path((paper.filename or "").strip()).name
    claims_pdf = filename.lower().endswith(".pdf") or paper.content_type == "application/pdf"
    if not claims_pdf:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only a PDF position paper can be uploaded."
        )

    limit_mb = core.storage.MAX_PAPER_BYTES // (1024 * 1024)
    if paper.size is not None and paper.size > core.storage.MAX_PAPER_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The PDF is larger than {limit_mb} MB.",
        )

    data = await paper.read()
    if len(data) > core.storage.MAX_PAPER_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The PDF is larger than {limit_mb} MB.",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That file is not a PDF."
        )

    stored_name = core.storage.new_paper_name(delegate.account_id)
    try:
        # Off the event loop: writing and fsyncing several megabytes would stall it.
        await run_in_threadpool(core.storage.save_paper, stored_name, data)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not store the upload. Check that the paper directory is writable.",
        ) from exc

    db.add(
        Uploads(
            delegate_id=delegate.account_id,
            file_name=filename[:256] or "position-paper.pdf",
            file_path=stored_name,  # relative to PAPER_UPLOAD_DIR, never absolute
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

    return {
        "message": "Position paper received.",
        "file_name": filename,
        "status": delegate.paper_status,
    }
