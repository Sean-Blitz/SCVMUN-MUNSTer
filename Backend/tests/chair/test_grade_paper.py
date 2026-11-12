"""Domain tests for ``core.domain.chairs.grade_paper``.

The endpoint can only show the resulting status code, so the rules that live in the use case
are pinned here:

* the total is **recomputed** as ``sum(marks) / sum(maxima)`` - the request has no say;
* every mark must name a criterion from the rubric and sit inside ``0..max``, with a hair of
  floating-point tolerance so full marks are never rejected;
* re-grading is allowed and the audit line distinguishes it from a first grade.

``CommentsTooLong`` is also tested here and nowhere else: the request model caps ``comments``
at the same 500 characters, so Pydantic rejects an over-long body before the domain sees it.
The domain check is what protects a script or a future caller that does not use the model.
"""

import pytest

import core.audit
from core.domain import chairs as domain
from core.domain.errors import (
    ChairNotFound,
    CommentsTooLong,
    DelegateNotInCommittee,
    PaperNotSubmitted,
    RubricNotConfigured,
    ScoreCriterionUnknown,
    ScoreOutOfRange,
)

PAPER_RUBRIC = [
    {"id": "clarity", "label": "Clarity", "maxScore": 10},
    {"id": "evidence", "label": "Evidence", "maxScore": 5},
    {"id": "style", "label": "Style", "maxScore": 5},
]


def _submitted_delegate(factory, committee, school, **fields):
    return factory.new_delegate(committee, school, paper_status="submitted", **fields)


def _grade(db, delegate, chair, *, scores, comments=""):
    return domain.grade_paper(
        db,
        chair.id,
        delegate.account_id,
        scores=scores,
        comments=comments,
        actor="chair:test",
    )


# --- the happy path --------------------------------------------------------------------


def test_the_total_is_recomputed_from_the_rubric(db, factory, chair, committee, school):
    """``17/20`` is ``8 + 4 + 5`` over ``10 + 5 + 5``; the caller supplied no total at all."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    outcome = _grade(
        db, delegate, chair, scores={"clarity": 8, "evidence": 4, "style": 5}, comments="Good."
    )

    assert outcome.total == "17/20"
    assert delegate.paper_grade == "17/20"
    assert delegate.paper_status == "graded"
    assert delegate.paper_rubric_grade == {"clarity": 8.0, "evidence": 4.0, "style": 5.0}


def test_comments_are_trimmed_and_blank_becomes_null(
    db, factory, chair, committee, school
):
    """The column is nullable; an empty string would render an empty block in the view."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    _grade(db, delegate, chair, scores={"clarity": 1}, comments="   ")

    assert delegate.paper_comments is None


def test_grading_everything_zero_is_legal(db, factory, chair, committee, school):
    """A poor paper is still a graded paper; the total reads ``0/20``, not blank."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    outcome = _grade(db, delegate, chair, scores={})

    assert outcome.total == "0/20"


def test_a_mark_equal_to_the_maximum_is_accepted(db, factory, chair, committee, school):
    """The tolerance exists so full marks are never lost to float representation."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    outcome = _grade(db, delegate, chair, scores={"clarity": 10, "evidence": 5, "style": 5})

    assert outcome.total == "20/20"


def test_numeric_criterion_ids_match_string_score_keys(
    db, factory, chair, committee, school
):
    """JSONB object keys are always strings, so an integer rubric id has to match ``"1"``."""
    factory.rubric(
        "paper", [{"id": 1, "label": "Clarity", "maxScore": 10}]
    )
    delegate = _submitted_delegate(factory, committee, school)

    _grade(db, delegate, chair, scores={"1": 6})

    assert delegate.paper_rubric_grade == {"1": 6.0}


def test_re_grading_replaces_the_previous_marks(db, factory, chair, committee, school):
    """A correction overwrites; the marks are not merged with the earlier attempt."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    _grade(db, delegate, chair, scores={"clarity": 4, "evidence": 4})
    outcome = _grade(db, delegate, chair, scores={"clarity": 9})

    assert outcome.total == "9/20"
    assert delegate.paper_rubric_grade == {"clarity": 9.0}


def test_the_audit_line_distinguishes_a_regrade(db, factory, chair, committee, school):
    """The business log is the record of what a chair changed; a correction must show as one."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    _grade(db, delegate, chair, scores={"clarity": 4})

    before = core.audit.read("business")
    _grade(db, delegate, chair, scores={"clarity": 9})
    written = core.audit.read("business")[len(before):]

    assert "grade.saved" in written
    assert "regrade=true" in written
    assert f"delegate={delegate.account_id}" in written


# --- refusals --------------------------------------------------------------------------


def test_an_account_without_a_chair_profile_cannot_grade(db, factory, committee, school):
    account = factory.account(role="chair", identifier="CHAIR-NO-GRADE")
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(ChairNotFound):
        domain.grade_paper(
            db, account.id, delegate.account_id, scores={}, comments="", actor="chair:x"
        )


def test_a_delegate_from_another_committee_cannot_be_graded(db, factory, chair, school):
    factory.rubric("paper", PAPER_RUBRIC)
    foreign = _submitted_delegate(factory, factory.committee("UNSC"), school)

    with pytest.raises(DelegateNotInCommittee):
        _grade(db, foreign, chair, scores={})


def test_an_unsubmitted_paper_cannot_be_graded(db, factory, chair, committee, school):
    """Checked before the rubric, so "not submitted" wins over "no rubric"."""
    delegate = factory.new_delegate(committee, school, paper_status="unsubmitted")

    with pytest.raises(PaperNotSubmitted):
        _grade(db, delegate, chair, scores={})


def test_grading_without_a_configured_rubric_is_refused(db, factory, chair, committee, school):
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(RubricNotConfigured):
        _grade(db, delegate, chair, scores={})


def test_a_criterion_that_left_the_rubric_carries_its_id(db, factory, chair, committee, school):
    """The exception names the bad key, because the endpoint puts it in the message."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(ScoreCriterionUnknown) as raised:
        _grade(db, delegate, chair, scores={"retired": 3})

    assert raised.value.criteria == ("retired",)


def test_a_mark_above_the_maximum_carries_label_maximum_and_value(
    db, factory, chair, committee, school
):
    """The endpoint builds "Clarity must be between 0 and 10; got 11." from these three."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(ScoreOutOfRange) as raised:
        _grade(db, delegate, chair, scores={"clarity": 11})

    assert (raised.value.label, raised.value.maximum, raised.value.got) == (
        "Clarity",
        "10",
        "11",
    )


def test_a_negative_mark_is_refused(db, factory, chair, committee, school):
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(ScoreOutOfRange):
        _grade(db, delegate, chair, scores={"style": -1})


def test_comments_over_the_column_limit_are_refused(db, factory, chair, committee, school):
    """Only reachable here: the request model's 500-character cap rejects a longer body first."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(CommentsTooLong) as raised:
        _grade(db, delegate, chair, scores={"clarity": 5}, comments="x" * 501)

    assert raised.value.limit == 500


def test_a_refused_grade_leaves_the_delegate_untouched(db, factory, chair, committee, school):
    """Nothing is committed before the last check, so a rejected grade writes no partial row."""
    factory.rubric("paper", PAPER_RUBRIC)
    delegate = _submitted_delegate(factory, committee, school)

    with pytest.raises(ScoreOutOfRange):
        _grade(db, delegate, chair, scores={"clarity": 11})

    assert delegate.paper_status == "submitted"
    assert delegate.paper_grade is None
    assert delegate.paper_rubric_grade is None


# --- display helper --------------------------------------------------------------------


def test_format_mark_drops_a_trailing_zero_and_keeps_real_decimals():
    """The same rendering appears in the stored grade and in the rejection message."""
    assert domain.format_mark(18.0) == "18"
    assert domain.format_mark(8.5) == "8.5"
    assert domain.format_mark(7.25) == "7.25"
    assert domain.format_mark(0) == "0"
