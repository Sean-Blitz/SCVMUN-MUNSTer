"""Serving a stored position paper as a download.

Three endpoints hand a PDF to a browser: the advisor's for a delegate in their school, the
chair's for a delegate in their committee, and the delegate's for their own paper. Deciding
*who* may ask is each module's business - what they share is here: finding the paper
currently in force, turning a missing row or a missing file into an honest 404, and
streaming the bytes with the right media type.

Where the files actually live is core.storage's job; this module only reads the path
recorded in the database and asks it to resolve that inside the upload directory.
"""

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import core.storage
from crud.database_schema import Uploads


def latest_paper(db: Session, delegate_account_id: int) -> Uploads | None:
    """The delegate's current paper, or None if they have never uploaded one.

    Uploads are append-only - every submission is its own row - so the newest row is the
    paper in force. `upload_id` breaks a tie when two rows share a timestamp.
    """
    return db.scalars(
        select(Uploads)
        .where(Uploads.delegate_id == delegate_account_id)
        .order_by(Uploads.upload_time.desc(), Uploads.upload_id.desc())
        .limit(1)
    ).first()


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
    upload = latest_paper(db, delegate_account_id)
    if upload is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No position paper has been submitted yet.",
        )

    path = core.storage.paper_path(upload.file_path)
    if not path.is_file():
        # The row exists but the bytes do not: the storage volume was restored from an
        # older backup, or the file was removed by hand. Say so instead of letting
        # FileResponse raise.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. The paper has to be uploaded again.",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=download_name or upload.file_name or "position-paper.pdf",
    )
