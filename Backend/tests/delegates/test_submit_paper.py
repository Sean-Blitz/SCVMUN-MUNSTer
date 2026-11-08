"""Domain tests for ``core.domain.delegates.submit_paper``.

The upload endpoint does two transport checks (filename looks like a PDF, the declared size)
and then hands the bytes here. Everything this file tests is therefore the *actual* rule
set: the graded lock, the rolling-window cap, the ``%PDF-`` signature, the size limit, the
filename cleanup, and the promise that a delegate's disk use stays at one paper.

Assertions on "nothing was written" matter as much as the happy path: a rejected upload that
still leaves a file behind is how a volume fills up during a conference.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

import core.audit
import core.storage
from core import controls
from core.domain import delegates as domain
from core.domain.errors import (
    DelegateNotFound,
    NotAPdf,
    PaperAlreadyGraded,
    PaperStorageFailed,
    PaperTooLarge,
    UploadRateLimited,
)
from crud.database_schema import Uploads
from crud.db import utcnow

PDF_BYTES = b"%PDF-1.4\n% a position paper\n%%EOF\n"


def submit(
    db,
    delegate,
    *,
    file_name: str = "position-paper.pdf",
    data: bytes = PDF_BYTES,
    actor: str = "delegate:test",
):
    """Call the use case the way the endpoint does, minus the multipart parsing."""
    return domain.submit_paper(
        db, delegate.account_id, file_name=file_name, data=data, actor=actor
    )


def upload_rows(db) -> list[Uploads]:
    return list(db.scalars(select(Uploads).order_by(Uploads.upload_id)).all())


# --- the happy path --------------------------------------------------------------------


def test_stores_the_bytes_and_marks_the_paper_submitted(db, delegate, papers_dir):
    """One call: one row, one file on disk, delegate status flipped, result reported back.

    The stored *file name* is generated (``delegate-<id>-<random>.pdf``) and never the
    client's; the client's name is kept on the row for display only. That separation is
    what makes a name like ``../../etc/passwd.pdf`` harmless.
    """
    result = submit(db, delegate, file_name="france-paper.pdf")

    assert result.file_name == "france-paper.pdf"
    assert result.status == "submitted"

    db.expire_all()
    rows = upload_rows(db)
    assert len(rows) == 1
    assert delegate.paper_status == "submitted"

    assert rows[0].file_name == "france-paper.pdf"
    assert rows[0].file_path != "france-paper.pdf"
    assert rows[0].file_path.startswith(f"delegate-{delegate.account_id}-")
    assert (papers_dir / rows[0].file_path).read_bytes() == PDF_BYTES


def test_writes_a_business_audit_line(db, delegate):
    """The submission is recorded in the business log, not just the database.

    The audit trail is what answers "was this paper already submitted before the deadline?"
    months later, and it is written by the domain - so a refactor that moves the upload
    elsewhere has to keep it.
    """
    submit(db, delegate, actor="delegate:42")

    line = core.audit.read("business")

    assert "paper.submitted" in line
    assert "actor=delegate:42" in line
    assert f"delegate={delegate.account_id}" in line


def test_each_upload_gets_a_fresh_stored_name(db, delegate):
    """Two uploads never share a stored name, so one cannot overwrite the other mid-race."""
    submit(db, delegate)
    first = upload_rows(db)[-1].file_path

    submit(db, delegate)
    second = upload_rows(db)[-1].file_path

    assert first != second


# --- refusals that must leave no trace -------------------------------------------------


def test_an_account_without_a_profile_cannot_submit(db, factory, papers_dir):
    account = factory.account(role="delegate", identifier="NO-PROFILE-2")

    with pytest.raises(DelegateNotFound):
        domain.submit_paper(
            db, account.id, file_name="p.pdf", data=PDF_BYTES, actor="delegate:x"
        )

    assert list(papers_dir.iterdir()) == []


def test_a_graded_paper_cannot_be_replaced(db, delegate, papers_dir):
    """The graded lock is enforced here, not only in the endpoint.

    It is checked *before* anything is read or written, so a refused upload costs one SELECT
    and leaves neither a row nor a file behind.
    """
    delegate.paper_status = "graded"
    db.commit()

    with pytest.raises(PaperAlreadyGraded):
        submit(db, delegate)

    assert upload_rows(db) == []
    assert list(papers_dir.iterdir()) == []


def test_bytes_without_the_pdf_signature_are_refused(db, delegate, papers_dir):
    """A PDF content type is a claim; the ``%PDF-`` prefix is the check that counts."""
    with pytest.raises(NotAPdf):
        submit(db, delegate, data=b"Dear chairs, please find my paper attached.")

    assert upload_rows(db) == []
    assert list(papers_dir.iterdir()) == []


def test_an_oversized_paper_is_refused_and_reports_the_limit(db, delegate, papers_dir, monkeypatch):
    """The exception carries the limit, which is what the endpoint puts in its message.

    ``PaperTooLarge`` is not a bare ``DomainError`` for exactly this reason - the transport
    layer must not hard-code "10" a second time.
    """
    monkeypatch.setattr(core.storage, "MAX_PAPER_BYTES", 2 * 1024 * 1024)
    oversized = b"%PDF-1.4\n" + b"x" * (2 * 1024 * 1024)

    with pytest.raises(PaperTooLarge) as raised:
        submit(db, delegate, data=oversized)

    assert raised.value.limit_mb == 2
    assert upload_rows(db) == []
    assert list(papers_dir.iterdir()) == []



def test_a_write_failure_is_reported_as_a_storage_failure(db, delegate, papers_dir, monkeypatch):
    """A full disk or a read-only upload directory is a domain error, not a crash.

    The endpoint maps ``PaperStorageFailed`` to a 500 that names the likely cause. Patched
    at ``core.storage.save_paper`` because the alternative - chmod-ing the directory
    read-only - is not portable and would leak into other tests.
    """

    def refuse(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(core.storage, "save_paper", refuse)

    with pytest.raises(PaperStorageFailed):
        submit(db, delegate)

    # The row is only added after the bytes land, so a failed write leaves no record.
    assert upload_rows(db) == []
    assert list(papers_dir.iterdir()) == []

# --- the rolling window ----------------------------------------------------------------


def test_uploading_is_refused_once_the_window_is_full(db, factory, delegate):
    """``MAX_UPLOADS_PER_HOUR`` rows already inside the hour block the next upload.

    The exception carries both numbers the endpoint needs: the limit for the sentence and
    the window for the ``Retry-After`` header.
    """
    for _ in range(controls.MAX_UPLOADS_PER_HOUR):
        factory.upload(delegate, when=utcnow())

    with pytest.raises(UploadRateLimited) as raised:
        submit(db, delegate)

    assert raised.value.limit == controls.MAX_UPLOADS_PER_HOUR
    assert raised.value.window_hours == domain.UPLOAD_WINDOW_HOURS


def test_uploads_older_than_the_window_do_not_count(db, factory, delegate):
    """The cap is a rolling hour, not "five ever".

    Five rows from two hours ago are history; the delegate may upload again.
    """
    for _ in range(controls.MAX_UPLOADS_PER_HOUR):
        factory.upload(delegate, when=utcnow() - timedelta(hours=2))

    result = submit(db, delegate)

    assert result.status == "submitted"


def test_the_limit_allows_exactly_max_uploads(db, factory, delegate):
    """Off-by-one pin: ``MAX - 1`` existing rows still allow one more upload.

    A cheap boundary test, because "at most five" is easy to implement as "fewer than five".
    """
    for _ in range(controls.MAX_UPLOADS_PER_HOUR - 1):
        factory.upload(delegate, when=utcnow())

    result = submit(db, delegate)

    assert result.status == "submitted"
    assert len(upload_rows(db)) == controls.MAX_UPLOADS_PER_HOUR


# --- the client's display name ---------------------------------------------------------


def test_a_path_in_the_filename_is_reduced_to_its_basename(db, delegate):
    """Path traversal in the display name is stripped; only the directory is removed.

    The stored file is already a generated name, so this protects the *chair's* download
    filename rather than the upload root.
    """
    result = submit(db, delegate, file_name="../../etc/passwd.pdf")

    assert result.file_name == "passwd.pdf"


def test_an_empty_filename_falls_back_to_a_default(db, delegate):
    """An empty filename is legal in multipart, so it must not produce an empty name."""
    result = submit(db, delegate, file_name="")

    assert result.file_name == "position-paper.pdf"


def test_a_very_long_filename_is_truncated(db, delegate):
    """The column is String(256); truncating here avoids a database error on a valid upload."""
    result = submit(db, delegate, file_name="x" * 400 + ".pdf")

    assert len(result.file_name) == 256


# --- disk footprint --------------------------------------------------------------------


def test_a_second_upload_prunes_the_first_file_but_keeps_both_rows(db, delegate, papers_dir):
    """History is rows; the disk keeps one paper per delegate.

    Two rows, one file, and the surviving bytes are the newer submission. Without the prune
    step a delegate could fill the volume by uploading repeatedly, because re-uploading is
    allowed until the paper is graded.
    """
    submit(db, delegate, data=b"%PDF-1.4\nfirst\n%%EOF\n")
    submit(db, delegate, data=b"%PDF-1.4\nsecond\n%%EOF\n")

    rows = upload_rows(db)
    assert len(rows) == 2

    files = [path for path in papers_dir.iterdir() if path.is_file()]
    assert len(files) == 1
    assert files[0].read_bytes() == b"%PDF-1.4\nsecond\n%%EOF\n"
    assert files[0].name == rows[-1].file_path
