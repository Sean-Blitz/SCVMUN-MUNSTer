"""
Delegate endpoints (/delegate/*) — Frontend-API-Contract.md §2.

Every route here is scoped to the calling delegate; the account comes from the token
rather than from the request body, so a delegate cannot request another's assignment.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from API.dependencies import CurrentUser, get_current_user, require_roles
from schemas.response_models import DelegateAssignmentResponse

router = APIRouter(
    prefix="/delegate",
    tags=["delegate"],
    dependencies=[Depends(require_roles("delegate"))],
)


@router.get("/my-assignment", response_model=DelegateAssignmentResponse)
def get_my_assignment(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DelegateAssignmentResponse:
    """
    Return everything the delegate dashboard renders: announcements, their committee
    and country, the conference links, and the position-paper panel state including the
    chair's grade and feedback.

    TODO: load the assignment for `user.id`. Return empty/absent collections rather
    than omitting keys — the template addresses them directly.

    TODO: once the paper is graded, join the chair's stored `scores` map against the
    grading rubric so `positionPaper.criteria` carries a ready-to-render row per
    criterion (id, label, score, maxScore). The delegate cannot call /chair/rubric —
    it is role-gated — so the labels have to be resolved here. Leave `criteria` empty
    while the paper is unsubmitted or awaiting grading.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


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
