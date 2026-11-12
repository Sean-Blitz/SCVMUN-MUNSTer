"""Domain tests for ``core.domain.advisors.get_paper_file``.

This function is where the advisor's *paper download* crosses two rules: the delegate must
belong to the caller's school, and the bytes must be the newest submission. The endpoint can
only show the resulting 404, so the distinctions between "not your delegate", "never
submitted" and "file gone" are pinned here.

The returned ``PaperFile`` is data - a path and a download name - which is what lets the
endpoint turn it into a ``FileResponse`` without the domain knowing about HTTP.
"""

import pytest

from core.domain import advisors as domain
from core.domain.errors import (
    DelegateNotInSchool,
    PaperFileMissing,
    PaperNotSubmitted,
    SchoolNotFound,
)
from crud.db import utcnow


def _delegate_in(factory, school, committee, *, identifier="DELEGATE-1", country="France"):
    return factory.delegate(
        factory.account(role="delegate", identifier=identifier),
        committee=committee,
        school=school,
        country=country,
    )


def test_an_advisor_without_a_school_raises_school_not_found(db, factory, committee, school):
    """The school is resolved first, so the failure names the real problem."""
    advisor = factory.account(role="advisor", identifier="ADV-NO-SCHOOL")
    delegate = _delegate_in(factory, school, committee)

    with pytest.raises(SchoolNotFound):
        domain.get_paper_file(db, advisor.id, delegate.account_id)


def test_a_delegate_from_another_school_raises_delegate_not_in_school(
    db, factory, advisor, school, committee
):
    """The lookup is scoped to the school, so a foreign delegate is simply not found."""
    rival = factory.account(role="advisor", identifier="ADV-RIVAL")
    rival_school = factory.school(rival, name="Rival High School")
    foreign = _delegate_in(factory, rival_school, committee, identifier="FOREIGN-1")

    with pytest.raises(DelegateNotInSchool):
        domain.get_paper_file(db, advisor.id, foreign.account_id)


def test_an_unknown_delegate_id_raises_the_same_error(db, advisor, school):
    """A nonexistent id and a foreign one are one failure, so there is no existence oracle."""
    with pytest.raises(DelegateNotInSchool):
        domain.get_paper_file(db, advisor.id, 999_999)


def test_a_delegate_who_never_submitted_raises_paper_not_submitted(
    db, factory, advisor, school, committee
):
    """Nothing uploaded is a different failure from a row whose bytes went missing."""
    delegate = _delegate_in(factory, school, committee)

    with pytest.raises(PaperNotSubmitted):
        domain.get_paper_file(db, advisor.id, delegate.account_id)


def test_the_returned_file_is_the_newest_upload(db, factory, advisor, school, committee):
    """Uploads are append-only; the live paper is the newest row."""
    delegate = _delegate_in(factory, school, committee)
    factory.upload(delegate, when=utcnow(), file_path="old.pdf", write_bytes=b"%PDF-old")
    factory.upload(delegate, when=utcnow(), file_path="new.pdf", write_bytes=b"%PDF-new")

    paper = domain.get_paper_file(db, advisor.id, delegate.account_id)

    assert paper.path.name == "new.pdf"
    assert paper.path.read_bytes() == b"%PDF-new"


def test_a_timestamp_tie_is_broken_by_upload_id(db, factory, advisor, school, committee):
    """Two rows can share a second; the higher ``upload_id`` is the newer submission.

    Without the tie-break the result would be whatever Postgres returned, which is how an
    advisor ends up looking at a paper the delegate already replaced.
    """
    delegate = _delegate_in(factory, school, committee)
    same_moment = utcnow()
    factory.upload(
        delegate, when=same_moment, file_path="first.pdf", write_bytes=b"%PDF-first"
    )
    factory.upload(
        delegate, when=same_moment, file_path="second.pdf", write_bytes=b"%PDF-second"
    )

    paper = domain.get_paper_file(db, advisor.id, delegate.account_id)

    assert paper.path.name == "second.pdf"


def test_a_row_whose_bytes_are_gone_raises_paper_file_missing(
    db, factory, advisor, school, committee, papers_dir
):
    """The row survived a restore the files did not; the advisor can ask for a re-upload."""
    delegate = _delegate_in(factory, school, committee)
    factory.upload(delegate, file_path="gone.pdf", write_bytes=b"%PDF-gone")
    (papers_dir / "gone.pdf").unlink()

    with pytest.raises(PaperFileMissing):
        domain.get_paper_file(db, advisor.id, delegate.account_id)


def test_a_stored_path_that_escapes_the_root_is_treated_as_missing(
    db, factory, advisor, school, committee
):
    """A corrupted ``file_path`` is a missing paper, never a read outside the upload root."""
    delegate = _delegate_in(factory, school, committee)
    factory.upload(delegate, file_path="../../etc/passwd")

    with pytest.raises(PaperFileMissing):
        domain.get_paper_file(db, advisor.id, delegate.account_id)


def test_the_download_name_is_built_from_the_delegate_id(
    db, factory, advisor, school, committee
):
    """The name is stable and unique per delegate, which is what a chair's inbox needs."""
    delegate = _delegate_in(factory, school, committee)
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    paper = domain.get_paper_file(db, advisor.id, delegate.account_id)

    assert paper.download_name == f"delegate_{delegate.account_id}_paper.pdf"


def test_the_path_points_inside_the_upload_directory(
    db, factory, advisor, school, committee, papers_dir
):
    """The domain hands back a resolved path under the configured root, not a relative name."""
    delegate = _delegate_in(factory, school, committee)
    factory.upload(delegate, file_path="nested/live.pdf", write_bytes=b"%PDF-nested")

    paper = domain.get_paper_file(db, advisor.id, delegate.account_id)

    assert paper.path.is_absolute()
    assert paper.path == (papers_dir / "nested" / "live.pdf").resolve()
