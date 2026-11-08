"""Domain tests for paper resolution: ``get_delegate_paper_file`` and ``core.domain.papers``.

"The paper in force" is one concept shared by the download endpoint, the dashboard's status
line, and the admin's "missing file" report. These tests pin it in one place: newest row
wins, a timestamp tie is broken by ``upload_id``, a row whose bytes are gone is *missing*
rather than an error, and pruning removes every file except the live one.

A row without a file is a real production state - a half-restored volume - so it is a test
case here, not a hypothetical.
"""

import pytest
from sqlalchemy import select

from core.domain import delegates as domain
from core.domain import papers
from core.domain.errors import (
    DelegateNotFound,
    PaperFileMissing,
    PaperNotSubmitted,
)
from crud.database_schema import Uploads
from crud.db import utcnow


def test_an_account_without_a_profile_has_no_paper(db, factory):
    account = factory.account(role="delegate", identifier="NO-PROFILE-3")

    with pytest.raises(DelegateNotFound):
        domain.get_delegate_paper_file(db, account.id)


def test_a_delegate_who_never_uploaded_has_no_paper(db, delegate):
    with pytest.raises(PaperNotSubmitted):
        domain.get_delegate_paper_file(db, delegate.account_id)


def test_returns_the_path_and_a_country_based_download_name(db, factory, delegate, papers_dir):
    """The filename follows the country, so a chair's inbox stays readable.

    It is only a fallback for a direct API call - the dashboard saves the blob under a name
    of its own - but it is part of the response, so it is pinned.
    """
    factory.upload(
        delegate, file_name="france.pdf", file_path="live.pdf", write_bytes=b"%PDF-live"
    )

    paper = domain.get_delegate_paper_file(db, delegate.account_id)

    assert paper.path == (papers_dir / "live.pdf").resolve()
    assert paper.path.read_bytes() == b"%PDF-live"
    assert paper.download_name == "France_Position_Paper.pdf"


def test_the_newest_upload_is_the_one_in_force(db, factory, delegate):
    """Uploads are append-only; the newest row is the live paper."""
    factory.upload(delegate, file_path="old.pdf", write_bytes=b"%PDF-old")
    factory.upload(delegate, file_path="new.pdf", write_bytes=b"%PDF-new")

    paper = domain.get_delegate_paper_file(db, delegate.account_id)

    assert paper.path.name == "new.pdf"


def test_a_timestamp_tie_is_broken_by_upload_id(db, factory, delegate):
    """Two rows can share a timestamp; the higher ``upload_id`` is the newer submission.

    Without the tie-break the ordering would be whatever Postgres happened to return, which
    is how a delegate ends up downloading the paper they just replaced.
    """
    same_moment = utcnow()
    factory.upload(delegate, when=same_moment, file_path="first.pdf", write_bytes=b"%PDF-1")
    factory.upload(delegate, when=same_moment, file_path="second.pdf", write_bytes=b"%PDF-2")

    paper = domain.get_delegate_paper_file(db, delegate.account_id)

    assert paper.path.name == "second.pdf"


def test_a_row_whose_bytes_are_gone_is_reported_as_missing(db, factory, delegate, papers_dir):
    """The database and the filesystem disagree; that is "missing", not a crash.

    The delegate can fix it by uploading again, which is why it is distinct from
    ``PaperNotSubmitted``: the two get different messages.
    """
    factory.upload(delegate, file_path="gone.pdf", write_bytes=b"%PDF-gone")
    (papers_dir / "gone.pdf").unlink()

    with pytest.raises(PaperFileMissing):
        domain.get_delegate_paper_file(db, delegate.account_id)


def test_a_stored_path_that_escapes_the_root_is_treated_as_missing(db, factory, delegate):
    """A corrupted ``file_path`` is a missing paper, never a read outside the upload root.

    ``core.storage.paper_path`` refuses the path; the domain turns that refusal into the
    same "missing" outcome, so a bad row cannot become a filesystem read.
    """
    factory.upload(delegate, file_path="../../etc/passwd")

    with pytest.raises(PaperFileMissing):
        domain.get_delegate_paper_file(db, delegate.account_id)


# --- has_file / prune_superseded_files -------------------------------------------------


def test_has_file_follows_the_bytes_not_the_row(db, factory, delegate, papers_dir):
    """The admin panel asks "is the live paper actually there?", not "is there a row?"."""
    assert papers.has_file(db, delegate.account_id) is False

    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")
    assert papers.has_file(db, delegate.account_id) is True

    (papers_dir / "live.pdf").unlink()
    assert papers.has_file(db, delegate.account_id) is False


def test_pruning_keeps_only_the_live_file_and_reports_what_it_removed(
    db, factory, delegate, papers_dir
):
    """Three rows, three files, one survivor - and the count is what the audit line logs."""
    factory.upload(delegate, file_path="one.pdf", write_bytes=b"%PDF-1")
    factory.upload(delegate, file_path="two.pdf", write_bytes=b"%PDF-2")
    factory.upload(delegate, file_path="three.pdf", write_bytes=b"%PDF-3")

    removed = papers.prune_superseded_files(db, delegate.account_id)

    assert removed == 2
    assert sorted(path.name for path in papers_dir.iterdir()) == ["three.pdf"]
    # The rows are history and stay; only the bytes are pruned.
    assert len(db.scalars(select(Uploads)).all()) == 3


def test_pruning_with_nothing_uploaded_is_a_no_op(db, delegate, papers_dir):
    """A fresh delegate has no live row, so there is nothing to keep and nothing to remove."""
    assert papers.prune_superseded_files(db, delegate.account_id) == 0
    assert list(papers_dir.iterdir()) == []
