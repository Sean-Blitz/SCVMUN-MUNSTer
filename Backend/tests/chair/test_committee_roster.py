"""Domain tests for the chair's grading reads: ``list_committee_delegates`` and
``get_paper_file``.

Two things here are only reachable below the HTTP layer:

* the roster narrows every upload to "the newest per delegate" in one query, and coerces the
  stored JSONB marks defensively - a hand-edited or half-migrated value must not take the
  page down;
* "the paper in force" is resolved through ``core.domain.papers``, which distinguishes "never
  submitted" from "row exists, bytes gone".
"""

from datetime import datetime

import pytest

from core.domain import chairs as domain
from core.domain.errors import (
    ChairNotFound,
    DelegateNotInCommittee,
    PaperFileMissing,
    PaperNotSubmitted,
)


# --- list_committee_delegates ----------------------------------------------------------


def test_an_account_without_a_chair_profile_raises_chair_not_found(db, factory):
    account = factory.account(role="chair", identifier="CHAIR-NO-ROSTER")

    with pytest.raises(ChairNotFound):
        domain.list_committee_delegates(db, account.id)


def test_only_the_chairs_committee_is_listed_in_country_order(
    db, factory, chair, committee, school
):
    for country in ("Spain", "Argentina"):
        factory.new_delegate(committee, school, country=country)
    factory.new_delegate(factory.committee("UNSC"), school, country="France")

    roster = domain.list_committee_delegates(db, chair.id)

    assert [entry.country for entry in roster] == ["Argentina", "Spain"]


def test_an_empty_committee_returns_an_empty_roster(db, chair):
    assert domain.list_committee_delegates(db, chair.id) == []


def test_the_roster_carries_the_stored_grading_state(
    db, factory, chair, committee, school
):
    delegate = factory.new_delegate(
        committee,
        school,
        paper_status="graded",
        paper_grade="18/20",
        paper_rubric_grade={"clarity": 10, "evidence": 8},
        paper_comments="Strong opening.",
    )

    entry = domain.list_committee_delegates(db, chair.id)[0]

    assert entry.id == delegate.account_id
    assert entry.status == "graded"
    assert entry.totalScore == "18/20"
    assert entry.scores == {"clarity": 10.0, "evidence": 8.0}
    assert entry.comments == "Strong opening."


def test_the_submission_date_is_the_newest_upload(db, factory, chair, committee, school):
    """Naive UTC in the column, an explicit offset in the payload, newest row wins."""
    delegate = factory.new_delegate(committee, school, paper_status="submitted")
    factory.upload(delegate, when=datetime(2026, 10, 4, 9, 0), file_path="old.pdf")
    factory.upload(delegate, when=datetime(2026, 10, 5, 9, 30), file_path="new.pdf")

    entry = domain.list_committee_delegates(db, chair.id)[0]

    assert entry.submissionDate == "2026-10-05T09:30:00+00:00"


def test_a_delegate_who_never_uploaded_has_an_empty_submission_date(
    db, factory, chair, committee, school
):
    factory.new_delegate(committee, school)

    assert domain.list_committee_delegates(db, chair.id)[0].submissionDate == ""


def test_non_numeric_marks_are_dropped_rather_than_breaking_the_roster(
    db, factory, chair, committee, school
):
    """The column is JSONB, so a hand-edit can put anything in it.

    One unreadable mark must cost that one criterion, not the whole page.
    """
    factory.new_delegate(
        committee,
        school,
        paper_rubric_grade={"clarity": "excellent", "evidence": 8, "style": None},
    )

    entry = domain.list_committee_delegates(db, chair.id)[0]

    assert entry.scores == {"evidence": 8.0}


def test_a_stored_value_that_is_not_an_object_reads_as_no_scores(
    db, factory, chair, committee, school
):
    """A list where the map belongs is corrupt data, not a reason to raise."""
    factory.new_delegate(committee, school, paper_rubric_grade=[])

    assert domain.list_committee_delegates(db, chair.id)[0].scores == {}


# --- get_paper_file --------------------------------------------------------------------


def test_an_account_without_a_chair_profile_cannot_download(db, factory, committee, school):
    account = factory.account(role="chair", identifier="CHAIR-NO-DOWNLOAD")
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(ChairNotFound):
        domain.get_paper_file(db, account.id, delegate.account_id)


def test_a_delegate_from_another_committee_raises_delegate_not_in_committee(
    db, factory, chair, school
):
    foreign = factory.new_delegate(factory.committee("UNSC"), school)
    factory.upload(foreign, file_path="foreign.pdf", write_bytes=b"%PDF-foreign")

    with pytest.raises(DelegateNotInCommittee):
        domain.get_paper_file(db, chair.id, foreign.account_id)


def test_an_unknown_delegate_id_raises_the_same_error(db, chair):
    """A nonexistent id and a foreign one are one failure, so ids cannot be probed."""
    with pytest.raises(DelegateNotInCommittee):
        domain.get_paper_file(db, chair.id, 999_999)


def test_a_delegate_who_never_submitted_raises_paper_not_submitted(
    db, factory, chair, committee, school
):
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(PaperNotSubmitted):
        domain.get_paper_file(db, chair.id, delegate.account_id)


def test_a_row_whose_bytes_are_gone_raises_paper_file_missing(
    db, factory, chair, committee, school, papers_dir
):
    delegate = factory.new_delegate(committee, school)
    factory.upload(delegate, file_path="gone.pdf", write_bytes=b"%PDF-gone")
    (papers_dir / "gone.pdf").unlink()

    with pytest.raises(PaperFileMissing):
        domain.get_paper_file(db, chair.id, delegate.account_id)


def test_the_newest_upload_is_the_file_served(db, factory, chair, committee, school):
    delegate = factory.new_delegate(committee, school)
    factory.upload(
        delegate, when=datetime(2026, 10, 1), file_path="old.pdf", write_bytes=b"%PDF-old"
    )
    factory.upload(
        delegate, when=datetime(2026, 10, 2), file_path="new.pdf", write_bytes=b"%PDF-new"
    )

    paper = domain.get_paper_file(db, chair.id, delegate.account_id)

    assert paper.path.read_bytes() == b"%PDF-new"


def test_the_download_name_follows_the_country(db, factory, chair, committee, school):
    """A chair's downloads folder stays readable when every file is named by country."""
    delegate = factory.new_delegate(committee, school, country="France")
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    paper = domain.get_paper_file(db, chair.id, delegate.account_id)

    assert paper.download_name == "France_Position_Paper.pdf"
