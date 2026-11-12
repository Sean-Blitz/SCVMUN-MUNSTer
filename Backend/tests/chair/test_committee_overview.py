"""Domain tests for ``core.domain.chairs.get_committee_overview``.

The counters and the timeline are the two things a chair looks at first, and both have a rule
that a status code cannot express:

* "papers submitted" counts graded papers too - it is "anything a chair can mark", not "waiting
  to be marked";
* the timeline is conference-wide, split by phase, sorted by time, and every timestamp carries
  an explicit UTC offset so a browser does not read the naive column as local time.
"""

from datetime import datetime

import pytest

import core.security
from core.domain import chairs as domain
from core.domain.errors import ChairNotFound
from crud.database_schema import TimelineEvent


# --- the profile -----------------------------------------------------------------------


def test_an_account_without_a_chair_profile_raises_chair_not_found(db, factory):
    """The committee is resolved from the ``chairs`` row; without it there is nothing to count."""
    account = factory.account(role="chair", identifier="CHAIR-NO-PROFILE")

    with pytest.raises(ChairNotFound):
        domain.get_committee_overview(db, account.id)


# --- the counters ----------------------------------------------------------------------


def test_the_counters_are_scoped_to_the_chairs_committee(db, factory, chair, committee, school):
    """A graded delegate in another committee is the control for all three counters."""
    factory.new_delegate(committee, school, country="Argentina", paper_status="submitted")
    factory.new_delegate(committee, school, country="France", paper_status="graded")
    factory.new_delegate(committee, school, country="Spain", paper_status="unsubmitted")
    factory.new_delegate(
        factory.committee("UNSC"), school, country="Italy", paper_status="graded"
    )

    overview = domain.get_committee_overview(db, chair.id)

    assert overview.totalDelegates == 3
    assert overview.papersGraded == 1
    assert overview.totalPapersSubmitted == 2


def test_a_graded_paper_still_counts_as_submitted(db, factory, chair, committee, school):
    """The dashboard renders ``papersGraded / totalPapersSubmitted``, so graded must count.

    Excluding it would make the line read "3 / 0" once every paper has been marked.
    """
    factory.new_delegate(committee, school, paper_status="graded")

    overview = domain.get_committee_overview(db, chair.id)

    assert overview.totalPapersSubmitted == 1
    assert overview.papersGraded == 1


def test_registered_counts_the_accounts_that_have_a_password(
    db, factory, chair, committee, school
):
    """"Registered" is the same definition the login screen uses: a non-NULL password hash."""
    factory.delegate(
        factory.account(
            role="delegate", password_hash=core.security.hash_password("Passw0rd!x")
        ),
        committee=committee,
        school=school,
        country="Argentina",
    )
    factory.new_delegate(committee, school, country="France")

    assert domain.get_committee_overview(db, chair.id).delegatesRegistered == 1


def test_an_empty_committee_reports_zeroes_rather_than_nulls(db, chair):
    """``count()`` returns None on no rows; the payload must still be a number."""
    overview = domain.get_committee_overview(db, chair.id)

    assert (
        overview.totalDelegates,
        overview.delegatesRegistered,
        overview.papersGraded,
        overview.totalPapersSubmitted,
    ) == (0, 0, 0, 0)


# --- the timeline ----------------------------------------------------------------------


def test_the_timeline_is_split_by_phase_and_sorted_by_time(db, factory, chair):
    """Insertion order is not time order, and the frontend relies on ascending time."""
    factory.db.add_all(
        [
            TimelineEvent(
                phase="preConference", label="Second", starts_at=datetime(2027, 1, 1, 9, 0)
            ),
            TimelineEvent(
                phase="duringConference", label="Conference", starts_at=datetime(2027, 2, 1)
            ),
            TimelineEvent(
                phase="preConference", label="First", starts_at=datetime(2026, 12, 1, 9, 0)
            ),
        ]
    )
    factory.db.commit()

    timeline = domain.get_committee_overview(db, chair.id).timeline

    assert [event.label for event in timeline.preConference] == ["First", "Second"]
    assert [event.label for event in timeline.duringConference] == ["Conference"]


def test_timestamps_are_rendered_with_an_explicit_utc_offset(db, factory, chair):
    """Without the offset, ``new Date("2026-12-01T09:00:00")`` is read as *local* time.

    That would shift every event by the viewer's timezone and make the
    completed/active/upcoming derivation wrong.
    """
    factory.db.add(
        TimelineEvent(
            phase="preConference", label="Kickoff", starts_at=datetime(2026, 12, 1, 9, 0)
        )
    )
    factory.db.commit()

    event = domain.get_committee_overview(db, chair.id).timeline.preConference[0]

    assert event.timestamp == "2026-12-01T09:00:00+00:00"


def test_both_phases_are_present_when_empty(db, chair):
    """The template iterates both keys directly, so neither may be missing."""
    timeline = domain.get_committee_overview(db, chair.id).timeline

    assert timeline.preConference == []
    assert timeline.duringConference == []


# --- the committee row -----------------------------------------------------------------


def test_type_and_topic_come_from_the_committee_row(db, chair, committee):
    """A chair profile carries only the committee's name; the rest is on the committee."""
    committee.committee_type = "General Assembly"
    committee.topic = "Maritime security in the Gulf of Guinea"
    db.commit()

    overview = domain.get_committee_overview(db, chair.id)

    assert overview.committeeType == "General Assembly"
    assert overview.topic == "Maritime security in the Gulf of Guinea"


def test_absent_type_and_topic_become_empty_strings(db, chair):
    """Both columns are optional; the page prints them and falls back to its own wording."""
    overview = domain.get_committee_overview(db, chair.id)

    assert overview.committeeType == ""
    assert overview.topic == ""
