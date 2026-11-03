"""
Delegate endpoints (/delegate/*) — Frontend-API-Contract.md §2.

Transport only: resolve the caller, call one use case, map the result to an HTTP response.
The work itself lives in `core.domain.delegates`, which knows nothing about FastAPI, and
every failure it raises is translated here by `_http_error`.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import core.audit
import core.storage
from API.dependencies import CurrentUser, get_current_user, require_roles
from core.domain import delegates as delegates_domain
from core.domain import errors as domain_errors
from crud.db import get_db
from schemas.response_models import DelegateAssignmentResponse

router = APIRouter(
    prefix="/delegate",
    tags=["delegate"],
    dependencies=[Depends(require_roles("delegate"))],
)


def _http_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a domain failure into the status code and body the contract documents.

    One place on purpose: the domain says *what* went wrong, this decides what that means
    over HTTP. Only the rate limit needs a header, which is the reason domain errors carry
    their data instead of a status code.
    """
    if isinstance(exc, domain_errors.DelegateNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No delegate profile is attached to this account.",
        )
    if isinstance(exc, domain_errors.PaperNotSubmitted):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No position paper has been submitted yet.",
        )
    if isinstance(exc, domain_errors.PaperFileMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. The paper has to be uploaded again.",
        )
    if isinstance(exc, domain_errors.PaperAlreadyGraded):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "This paper has already been graded and cannot be replaced.",
        )
    if isinstance(exc, domain_errors.UploadRateLimited):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You can upload a position paper at most {exc.limit} "
            f"{'time' if exc.limit == 1 else 'times'} per "
            f"{'hour' if exc.window_hours == 1 else f'{exc.window_hours} hours'}.",
            headers={"Retry-After": str(exc.window_hours * 3600)},
        )
    if isinstance(exc, domain_errors.NotAPdf):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "That file is not a PDF.")
    if isinstance(exc, domain_errors.PaperTooLarge):
        return HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The PDF is larger than {exc.limit_mb} MB.",
        )
    if isinstance(exc, domain_errors.PaperStorageFailed):
        return HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not store the upload. Check that the paper directory is writable.",
        )
    # An unmapped domain error is a programming mistake, not a bad request.
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


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
    payload = delegates_domain.get_delegate_dashboard(db, user.id)
    if payload is None:
        raise _http_error(domain_errors.DelegateNotFound())
    return payload


@router.get("/my-paper")
def download_my_paper(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Return the caller's own position paper as a PDF blob.

    Scoped by the token rather than by a path parameter, so a delegate can only ever fetch
    their own paper. The newest upload is served - the one /delegate/my-assignment reports
    the status of - and the two 404s distinguish "nothing was uploaded" from "the stored
    file has gone missing".
    """
    try:
        paper = delegates_domain.get_delegate_paper_file(db, user.id)
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc

    return FileResponse(
        paper.path,
        media_type="application/pdf",
        filename=paper.download_name or "position-paper.pdf",
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

    Uploading again is allowed until a chair has graded the paper; each attempt is kept as
    its own `position_papers` row, so the newest is the live paper. Once it is graded it can
    no longer be replaced. At most `MAX_UPLOADS_PER_HOUR` uploads are accepted in a rolling
    hour, and each one deletes the delegate's previous file - the rules themselves live in
    `core.domain.delegates.submit_paper`.

    The two checks kept here are about the *transport*: the filename and content type are
    multipart metadata, and rejecting an oversized part before reading it into memory avoids
    buffering a file the domain is going to refuse anyway.
    """
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

    try:
        # Off the event loop: writing and fsyncing several megabytes would stall it.
        result = await run_in_threadpool(
            delegates_domain.submit_paper,
            db,
            user.id,
            file_name=filename,
            data=data,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _http_error(exc) from exc

    return {
        "message": "Position paper received.",
        "file_name": result.file_name,
        "status": result.status,
    }
