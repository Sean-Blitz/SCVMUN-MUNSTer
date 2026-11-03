"""Which position paper is in force, and where its bytes are.

This used to live in `API/papers.py` alongside the download response. The split is the
boundary in miniature: *which row is live* and *where the file is* are domain questions,
while turning that into a `FileResponse` and choosing a 404 message is transport.

Uploads are append-only - every submission is its own row - so "the paper in force" is the
newest row. `upload_id` breaks a tie when two rows share a timestamp.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.storage
from core.domain.errors import PaperFileMissing, PaperNotSubmitted
from crud.database_schema import Uploads


@dataclass(frozen=True)
class PaperFile:
    """A paper's bytes, resolved but not yet turned into a response."""

    path: Path
    download_name: str | None  # what the browser should suggest; None means "pick a default"


def latest_paper(db: Session, delegate_account_id: int) -> Uploads | None:
    """The delegate's current paper row, or None if they have never uploaded one."""
    return db.scalars(
        select(Uploads)
        .where(Uploads.delegate_id == delegate_account_id)
        .order_by(Uploads.upload_time.desc(), Uploads.upload_id.desc())
        .limit(1)
    ).first()


def paper_in_force(db: Session, delegate_account_id: int) -> PaperFile:
    """The bytes behind the live paper row, or the domain error explaining why there are none.

    Two separate failures on purpose: never submitting, and a row whose file went missing
    (a restored volume, a manual delete). The endpoints report them differently because the
    delegate can act on one of them and not the other.
    """
    upload = latest_paper(db, delegate_account_id)
    if upload is None:
        raise PaperNotSubmitted()

    try:
        path = core.storage.paper_path(upload.file_path)
    except ValueError:
        # A stored path that escapes the upload directory is a corrupted row, not a file.
        raise PaperFileMissing() from None

    if not path.is_file():
        raise PaperFileMissing()

    return PaperFile(path=path, download_name=upload.file_name)


def prune_superseded_files(db: Session, delegate_account_id: int) -> int:
    """Delete every stored file for the delegate except the one in force.

    Uploads are append-only rows, but only the newest file is kept, so a delegate's disk use
    is one paper. Doing this by *re-reading* the rows after the writing request commits -
    rather than deleting a list captured before it - is what makes two overlapping uploads
    agree: whichever request finishes last deletes everything that is not the newest row's
    file, so both keep the same survivor instead of each keeping its own.

    Returns how many files it asked to remove. Called after the upload commits, so a failure
    here must not fail the upload: an orphan is harmless and the next upload sweeps it up.
    """
    live = latest_paper(db, delegate_account_id)
    if live is None:
        return 0

    superseded = db.scalars(
        select(Uploads.file_path).where(
            Uploads.delegate_id == delegate_account_id,
            Uploads.upload_id != live.upload_id,
        )
    ).all()

    for stale in superseded:
        # Best-effort by design: a file that is already gone is not a failure.
        core.storage.delete_paper(stale)

    return len(superseded)
