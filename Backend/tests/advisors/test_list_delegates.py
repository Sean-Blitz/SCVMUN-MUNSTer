"""Domain tests for ``core.domain.advisors.list_delegates``.

The endpoint returns the same payload, so what is pinned here is the part a status code
cannot show: which rows the query selected, what each field is sourced from, and the masking
rule that must hold even if a future handler forgets to apply it.

The scoping and ordering rules live in the domain, not the endpoint, which is precisely why
they are tested at this level.
"""

import pytest

import core.security
from core.domain import advisors as domain
from core.domain.advisors import MASKED_HASH
from core.domain.errors import SchoolNotFound


def test_an_advisor_without_a_school_raises_school_not_found(db, factory):
    """The school is resolved from the account; without a row there is nothing to scope to.

    An exception rather than an empty roster: "you have no school" and "your school has no
    delegates" are different situations and the endpoint reports them differently.
    """
    account = factory.account(role="advisor", identifier="ADV-NO-SCHOOL")

    with pytest.raises(SchoolNotFound):
        domain.list_delegates(db, account.id)


def test_a_school_with_no_delegates_has_an_empty_roster(db, advisor, school):
    """An empty roster is a valid answer, not a failure: total counts what came back."""
    roster = domain.list_delegates(db, advisor.id)

    assert roster.delegates == []
    assert roster.total == 0


def test_only_the_advisors_own_school_is_listed(db, factory, advisor, school, committee):
    """The join is on ``delegates.school_id``, which is the owning advisor's account id."""
    mine = factory.delegate(
        factory.account(role="delegate", identifier="MINE-1"),
        committee=committee,
        school=school,
        country="France",
    )
    rival = factory.account(role="advisor", identifier="ADV-RIVAL")
    rival_school = factory.school(rival, name="Rival High School")
    factory.delegate(
        factory.account(role="delegate", identifier="THEIRS-1"),
        committee=committee,
        school=rival_school,
        country="Spain",
    )

    roster = domain.list_delegates(db, advisor.id)

    assert roster.total == 1
    assert [entry.id for entry in roster.delegates] == [mine.account_id]


def test_every_hash_is_masked(db, factory, advisor, school, committee):
    """The masked value is substituted in the domain, not left to the handler.

    The real identifier is asserted against the whole serialised payload, because a leak in
    any field is still a leak - the JSON is readable in devtools whatever the page renders.
    """
    factory.delegate(
        factory.account(role="delegate", identifier="SECRET-HASH-1234"),
        committee=committee,
        school=school,
    )

    roster = domain.list_delegates(db, advisor.id)

    assert roster.delegates[0].hash == MASKED_HASH
    assert "SECRET-HASH-1234" not in roster.model_dump_json()


def test_registered_is_the_presence_of_a_password_hash(
    db, factory, advisor, school, committee
):
    """``password_hash IS NOT NULL`` is the whole definition of "has registered".

    It is what tells an advisor who still has to claim their access code, so both directions
    are pinned.
    """
    factory.delegate(
        factory.account(role="delegate", identifier="UNREG-1"),
        committee=committee,
        school=school,
        country="Argentina",
    )
    factory.delegate(
        factory.account(
            role="delegate",
            identifier="REG-1",
            password_hash=core.security.hash_password("Passw0rd!x"),
        ),
        committee=committee,
        school=school,
        country="France",
    )

    roster = domain.list_delegates(db, advisor.id)

    assert {entry.country: entry.registered for entry in roster.delegates} == {
        "Argentina": False,
        "France": True,
    }


def test_the_entry_id_is_the_delegate_account_id(db, factory, advisor, school, committee):
    """The id the roster exposes is the one ``/delegates/{id}/paper`` takes back.

    ``delegates`` uses the account id as its primary key, so this is easy to get right and
    easy to break by switching to a surrogate column later.
    """
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="ID-1"),
        committee=committee,
        school=school,
    )

    roster = domain.list_delegates(db, advisor.id)

    assert roster.delegates[0].id == delegate.account_id


def test_the_roster_is_ordered_by_committee_then_country(
    db, factory, advisor, school, committee
):
    """A stable order, so the list does not reshuffle between two page loads."""
    unsc = factory.committee("UNSC")
    for committee_row, country in (
        (unsc, "France"),
        (committee, "France"),
        (committee, "Argentina"),
    ):
        factory.delegate(
            factory.account(role="delegate"),
            committee=committee_row,
            school=school,
            country=country,
        )

    roster = domain.list_delegates(db, advisor.id)

    assert [(entry.committee, entry.country) for entry in roster.delegates] == [
        ("DISEC", "Argentina"),
        ("DISEC", "France"),
        ("UNSC", "France"),
    ]


def test_paper_status_and_grade_are_carried_through(
    db, factory, advisor, school, committee
):
    """The roster doubles as the advisor's progress tracker."""
    factory.delegate(
        factory.account(role="delegate", identifier="GRADED-1"),
        committee=committee,
        school=school,
        paper_status="graded",
        paper_grade="18/20",
    )

    entry = domain.list_delegates(db, advisor.id).delegates[0]

    assert entry.paperStatus == "graded"
    assert entry.paperGrade == "18/20"


def test_total_matches_the_delegates_returned(db, factory, advisor, school, committee):
    """``total`` is computed from the same rows, so it cannot drift from the list."""
    for country in ("Argentina", "France", "Spain"):
        factory.delegate(
            factory.account(role="delegate"),
            committee=committee,
            school=school,
            country=country,
        )

    roster = domain.list_delegates(db, advisor.id)

    assert roster.total == len(roster.delegates) == 3


def test_the_roster_does_not_carry_the_account_name(
    db, factory, advisor, school, committee
):
    """The payload is deliberately narrow: country, committee, paper state, hash, registered.

    Pinning the absence keeps a future ``AdvisorDelegate(name=...)`` from quietly widening
    what every advisor can read about every delegate.
    """
    factory.delegate(
        factory.account(role="delegate", identifier="NARROW-1", name="Should Not Appear"),
        committee=committee,
        school=school,
    )

    entry = domain.list_delegates(db, advisor.id).delegates[0]

    assert "name" not in entry.model_dump()
    assert "Should Not Appear" not in entry.model_dump_json()
