"""Domain tests for the awards half of ``core.domain.chairs``.

The two rules worth stating precisely:

* an **official** award may only be stored once every rubric criterion has been scored - the
  frontend greys the button out, and this is the enforcement a script cannot bypass;
* ``None`` and ``Candidate`` are legitimate final states, so they need no scores and leave
  ``overall_total_score`` NULL rather than 0.0, which is what keeps the "n pts" badge hidden.

The stored total is recomputed from the marks, and the roster coerces the JSONB map the same
way the grading roster does.
"""

import pytest

import core.audit
from core.domain import chairs as domain
from core.domain.errors import (
    AwardCriteriaUnscored,
    AwardNotAssignable,
    ChairNotFound,
    DelegateNotInCommittee,
    ScoreCriterionUnknown,
)

AWARDS_RUBRIC = [
    {"id": "speaking", "label": "Speaking", "levels": [{"score": 4, "label": "Excellent"}]},
    {"id": "diplomacy", "label": "Diplomacy", "levels": [{"score": 3, "label": "Strong"}]},
]


def _award(db, delegate, chair, *, award, scores):
    return domain.assign_award(
        db,
        chair.id,
        delegate.account_id,
        award=award,
        scores=scores,
        actor="chair:test",
    )


# --- assignable_awards -----------------------------------------------------------------


def test_assignable_awards_skip_the_reserved_names_in_order():
    """``None`` and ``Candidate`` are the template's own options, not awards to hand out."""
    names = domain.assignable_awards()

    assert "None" not in names
    assert "Candidate" not in names
    assert names == [
        "Verbal Commendation",
        "Honorable Mention",
        "Outstanding Delegate",
        "Best Delegate",
    ]


def test_the_published_options_are_the_assignable_ones():
    """One source of truth: the endpoint publishes exactly what ``assign_award`` validates."""
    assert domain.list_award_options() == domain.assignable_awards()


def test_reserved_names_are_filtered_case_insensitively_and_blanked_entries_dropped(
    monkeypatch,
):
    """A bad entry in ``core.controls`` must not reach the dropdown."""
    from core import controls

    monkeypatch.setattr(
        controls, "award_options", ["None", "candidate", "   ", " Best Delegate "]
    )

    assert domain.assignable_awards() == ["Best Delegate"]


# --- list_award_delegates --------------------------------------------------------------


def test_an_account_without_a_chair_profile_cannot_list_awards(db, factory):
    account = factory.account(role="chair", identifier="CHAIR-NO-AWARDS")

    with pytest.raises(ChairNotFound):
        domain.list_award_delegates(db, account.id)


def test_an_unawarded_delegate_reads_as_none_with_a_hidden_total(
    db, factory, chair, committee, school
):
    """``totalScore`` None, not 0.0: a zero would show a "0 pts" badge on everyone."""
    factory.new_delegate(committee, school)

    entry = domain.list_award_delegates(db, chair.id)[0]

    assert entry.assignedAward == "None"
    assert entry.totalScore is None
    assert entry.scores == {}


def test_awarded_scores_and_total_are_reported(db, factory, chair, committee, school):
    factory.new_delegate(
        committee,
        school,
        assigned_award="Best Delegate",
        overall_rubric_scores={"speaking": 4, "diplomacy": 3},
        overall_total_score=7,
    )

    entry = domain.list_award_delegates(db, chair.id)[0]

    assert entry.assignedAward == "Best Delegate"
    assert entry.scores == {"speaking": 4.0, "diplomacy": 3.0}
    assert entry.totalScore == 7.0


def test_the_award_roster_is_scoped_and_ordered(db, factory, chair, committee, school):
    for country in ("Spain", "Argentina"):
        factory.new_delegate(committee, school, country=country)
    factory.new_delegate(factory.committee("UNSC"), school, country="France")

    roster = domain.list_award_delegates(db, chair.id)

    assert [entry.country for entry in roster] == ["Argentina", "Spain"]


def test_non_numeric_award_marks_are_dropped(db, factory, chair, committee, school):
    factory.new_delegate(
        committee,
        school,
        overall_rubric_scores={"speaking": "great", "diplomacy": 3},
        overall_total_score=3,
    )

    assert domain.list_award_delegates(db, chair.id)[0].scores == {"diplomacy": 3.0}


# --- assign_award ----------------------------------------------------------------------


def test_an_official_award_stores_the_marks_and_the_recomputed_total(
    db, factory, chair, committee, school
):
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    outcome = _award(
        db, delegate, chair, award="Best Delegate", scores={"speaking": 4, "diplomacy": 3}
    )

    assert outcome.award == "Best Delegate"
    assert outcome.total == 7.0
    assert delegate.assigned_award == "Best Delegate"
    assert delegate.overall_rubric_scores == {"speaking": 4.0, "diplomacy": 3.0}
    assert delegate.overall_total_score == 7.0


def test_none_needs_no_scores_and_leaves_the_total_null(
    db, factory, chair, committee, school
):
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school, overall_total_score=7)

    outcome = _award(db, delegate, chair, award="None", scores={})

    assert outcome.award == "None"
    assert outcome.total is None
    assert delegate.overall_total_score is None


def test_candidate_needs_no_scores(db, factory, chair, committee, school):
    """The shortlist is a state a chair saves before deciding, so it cannot be blocked."""
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    outcome = _award(db, delegate, chair, award="Candidate", scores={})

    assert outcome.award == "Candidate"
    assert delegate.assigned_award == "Candidate"


def test_none_with_scores_still_stores_them(db, factory, chair, committee, school):
    """Only the *missing criteria* check is skipped for the reserved names, not the marks."""
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    outcome = _award(db, delegate, chair, award="None", scores={"speaking": 4})

    assert outcome.total == 4.0
    assert delegate.overall_rubric_scores == {"speaking": 4.0}


def test_an_unknown_award_name_carries_the_allowed_list(
    db, factory, chair, committee, school
):
    """The endpoint renders these into "assignedAward must be one of: ..."."""
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(AwardNotAssignable) as raised:
        _award(db, delegate, chair, award="Participation Trophy", scores={})

    assert "Best Delegate" in raised.value.allowed
    assert "Candidate" in raised.value.allowed
    assert "None" in raised.value.allowed


def test_an_official_award_with_a_missing_criterion_names_what_is_missing(
    db, factory, chair, committee, school
):
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(AwardCriteriaUnscored) as raised:
        _award(db, delegate, chair, award="Best Delegate", scores={"speaking": 4})

    assert raised.value.award == "Best Delegate"
    assert raised.value.missing == ("Diplomacy",)


def test_an_unknown_criterion_carries_its_id(db, factory, chair, committee, school):
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(ScoreCriterionUnknown) as raised:
        _award(
            db,
            delegate,
            chair,
            award="Candidate",
            scores={"retired": 2, "speaking": 4, "diplomacy": 3},
        )

    assert raised.value.criteria == ("retired",)


def test_re_assigning_replaces_the_scores_rather_than_merging(
    db, factory, chair, committee, school
):
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)

    _award(db, delegate, chair, award="Best Delegate", scores={"speaking": 4, "diplomacy": 3})
    outcome = _award(
        db, delegate, chair, award="Outstanding Delegate", scores={"speaking": 2, "diplomacy": 3}
    )

    assert delegate.assigned_award == "Outstanding Delegate"
    assert delegate.overall_rubric_scores == {"speaking": 2.0, "diplomacy": 3.0}
    assert outcome.total == 5.0


def test_a_delegate_from_another_committee_cannot_be_awarded(db, factory, chair, school):
    factory.rubric("awards", AWARDS_RUBRIC)
    foreign = factory.new_delegate(factory.committee("UNSC"), school)

    with pytest.raises(DelegateNotInCommittee):
        _award(db, foreign, chair, award="Candidate", scores={})


def test_an_account_without_a_chair_profile_cannot_award(db, factory, committee, school):
    account = factory.account(role="chair", identifier="CHAIR-NO-AWARD")
    delegate = factory.new_delegate(committee, school)

    with pytest.raises(ChairNotFound):
        domain.assign_award(
            db,
            account.id,
            delegate.account_id,
            award="Candidate",
            scores={},
            actor="chair:x",
        )


def test_an_assignment_is_written_to_the_business_log(
    db, factory, chair, committee, school
):
    """Who handed out which award has to be answerable after the conference."""
    factory.rubric("awards", AWARDS_RUBRIC)
    delegate = factory.new_delegate(committee, school)
    before = core.audit.read("business")

    _award(db, delegate, chair, award="Best Delegate", scores={"speaking": 4, "diplomacy": 3})

    written = core.audit.read("business")[len(before):]
    assert "award.assigned" in written
    assert "award=Best_Delegate" in written or 'award="Best Delegate"' in written
    assert f"delegate={delegate.account_id}" in written
