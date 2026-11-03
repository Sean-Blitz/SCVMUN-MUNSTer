"""Turning "the delegate's paper in force" into a downloadable response.

Three endpoints hand a PDF to a browser: the advisor's for a delegate in their school, the
chair's for a delegate in their committee, and the delegate's for their own paper. Deciding
*who* may ask is each module's business, and *which row is live* is now the domain's
(`core.domain.papers`); what is left here is transport: pick a 404 message and stream the
bytes with the right media type and filename.

`latest_paper` is re-exported because the admin views use it directly.
"""

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.domain import errors as domain_errors
from core.domain.papers import (
    PaperFile,
    latest_paper,
    paper_in_force,
    prune_superseded_files,
)

__all__ = [
    "PaperFile",
    "latest_paper",
    "paper_in_force",
    "prune_superseded_files",
    "paper_response",
]


def paper_response(
    db: Session,
    delegate_account_id: int,
    *,
    download_name: str | None = None,
) -> FileResponse:
    """Stream the delegate's current paper as application/pdf.

    `download_name` is what the browser suggests in its save dialog; it defaults to the
    name the delegate uploaded under. The caller has already established that the delegate
    is someone this user is allowed to read (their school, their committee, or themselves).
    """
    try:
        paper = paper_in_force(db, delegate_account_id)
    except domain_errors.PaperNotSubmitted as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No position paper has been submitted yet.",
        ) from exc
    except domain_errors.PaperFileMissing as exc:
        # The row exists but the bytes do not: the storage volume was restored from an
        # older backup, or the file was removed by hand.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. The paper has to be uploaded again.",
        ) from exc

    return FileResponse(
        paper.path,
        media_type="application/pdf",
        filename=download_name or paper.download_name or "position-paper.pdf",
    )
