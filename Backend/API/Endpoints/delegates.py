"""
Delegate endpoints (/delegate/*) — Frontend-API-Contract.md §2.

Every route here is scoped to the calling delegate; the account comes from the token
rather than from the request body, so a delegate cannot request another's assignment.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
from core.controls import paper_rubric_data
from crud.database_schema import Broadcast, Delegates
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
) -> dict[str, str]:
    """
    Accept the delegate's position paper as multipart/form-data under the field name
    `paper`, then mark their submission as received.

    TODO: validate the upload is a PDF, store it, and set the delegate's paper status
    to 'submitted'. The frontend ignores this response body; errors surface as a toast.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")
