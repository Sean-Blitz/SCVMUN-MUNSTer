"""Domain tests for ``core.domain.admin.rubrics`` (§8.11): the two conference-wide documents.

The rule worth its own file is the **orphan check**. Every recorded mark is filed under a
criterion ``id``, so dropping or renaming an id that is already graded would strand real work:
the delegate's breakdown silently loses that line (``core.domain.delegates._paper_criteria``
joins the rubric against the stored marks). Such a save is refused with the affected ids, and
``force`` is the admin's explicit override.

The rest is validation the request model cannot express: a repeated id, a blank id, a blank
label, and a blank level label - each needing wording that names the criterion rather than a
JSON path.
"""

import pytest

import core.audit
from core.domain import rubrics as rubric_docs
from core.domain.admin import rubrics
from core.domain.errors import NothingToUpdate, RubricCriterionInUse, RubricInvalid
from crud.database_schema import Rubric

PAPER = [{"id": "clarity", "label": "Clarity", "maxScore": 10}]
AWARDS = [
    {"id": "speaking", "label": "Speaking", "levels": [{"score": 4, "label": "Excellent"}]}
]


def _replace(db, **kwargs):
    kwargs.setdefault("actor", "admin:1")
    return rubrics.replace(db, **kwargs)


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def test_one_document_at_a_time(db):
    """The two editors are independent: saving one must not clobber the other."""
    _replace(db, paper=PAPER)

    result = _replace(db, awards=AWARDS)

    assert [criterion.id for criterion in result.paper] == ["clarity"]
    assert [criterion.id for criterion in result.awards] == ["speaking"]


def test_an_omitted_rubric_is_untouched(db):
    _replace(db, paper=PAPER, awards=AWARDS)

    result = _replace(db, paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}])

    assert [criterion.id for criterion in result.paper] == ["evidence"]
    assert [criterion.id for criterion in result.awards] == ["speaking"]


def test_an_empty_list_empties_a_rubric(db):
    """`[]` is an answer ("no criteria"); omitting the key is not."""
    _replace(db, paper=PAPER)

    assert _replace(db, paper=[]).paper == []


def test_sending_neither_is_refused(db):
    with pytest.raises(NothingToUpdate):
        _replace(db)


def test_the_stored_document_records_who_saved_it(db):
    _replace(db, paper=PAPER)

    assert rubric_docs.read(db, rubric_docs.PAPER) == PAPER

    row = db.get(Rubric, "paper")
    assert row.updated_by == "admin:1"
    assert row.updated_at is not None


def test_saving_is_audited(db):
    """Handing the graders a new rubric is a business event, not just a settings change."""
    before = core.audit.read("business")

    _replace(db, paper=PAPER)

    written = core.audit.read("business")[len(before):]
    assert "rubric.saved" in written
    assert "kind=paper" in written


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_a_repeated_id_is_refused(db):
    """Every mark is filed under the id, so a duplicate would make it ambiguous."""
    with pytest.raises(RubricInvalid) as raised:
        _replace(
            db,
            paper=[
                {"id": "clarity", "label": "Clarity", "maxScore": 10},
                {"id": "clarity", "label": "Again", "maxScore": 5},
            ],
        )

    assert "more than once" in raised.value.detail


def test_a_blank_id_is_refused(db):
    with pytest.raises(RubricInvalid) as raised:
        _replace(db, paper=[{"id": "   ", "label": "Clarity", "maxScore": 10}])

    assert "needs an id" in raised.value.detail


def test_a_blank_label_is_refused(db):
    with pytest.raises(RubricInvalid) as raised:
        _replace(db, paper=[{"id": "clarity", "label": "  ", "maxScore": 10}])

    assert "needs a label" in raised.value.detail


def test_a_blank_level_label_is_refused(db):
    with pytest.raises(RubricInvalid) as raised:
        _replace(
            db,
            awards=[
                {
                    "id": "speaking",
                    "label": "Speaking",
                    "levels": [{"score": 4, "label": "   "}],
                }
            ],
        )

    assert "needs a label" in raised.value.detail


def test_ids_and_labels_are_stripped_before_storing(db):
    """The stored document is what the editor typed, not what it typed plus spaces."""
    result = _replace(
        db,
        paper=[{"id": "  clarity  ", "label": "  Clarity  ", "maxScore": 10}],
    )

    assert (result.paper[0].id, result.paper[0].label) == ("clarity", "Clarity")


def test_a_numeric_id_is_compared_as_a_string(db, factory, committee, school):
    """JSONB object keys are always strings, so a mark filed under ``"1"`` matches id ``1``.

    Without the string comparison a rubric with numeric ids would never match its own stored
    marks and the orphan check would silently pass.
    """
    factory.new_delegate(committee, school, paper_rubric_grade={"1": 6})

    with pytest.raises(RubricCriterionInUse):
        _replace(db, paper=[{"id": 2, "label": "Evidence", "maxScore": 5}])


# ---------------------------------------------------------------------------
# The orphan check
# ---------------------------------------------------------------------------


def test_dropping_an_unmarked_criterion_is_fine(db, factory, committee, school):
    """A paper that was graded by comment only leaves no marks, so nothing can be orphaned."""
    factory.new_delegate(committee, school, paper_status="graded")

    result = _replace(db, paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}])

    assert [criterion.id for criterion in result.paper] == ["evidence"]


def test_dropping_a_marked_criterion_names_it(db, factory, committee, school):
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6})

    with pytest.raises(RubricCriterionInUse) as raised:
        _replace(db, paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}])

    assert "clarity" in str(raised.value)


def test_the_awards_orphans_are_tracked_separately(db, factory, committee, school):
    """A mark in ``overall_rubric_scores`` belongs to the awards rubric, not the paper one."""
    factory.new_delegate(committee, school, overall_rubric_scores={"speaking": 4})

    with pytest.raises(RubricCriterionInUse):
        _replace(db, awards=[{"id": "diplomacy", "label": "Diplomacy", "levels": [{"score": 3, "label": "Strong"}]}])

    # The paper rubric has nothing recorded against it, so it saves freely.
    assert _replace(db, paper=PAPER).paper


def test_force_saves_over_recorded_marks(db, factory, committee, school):
    """The override is explicit: the marks stay, but leave the breakdown."""
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6})

    result = _replace(
        db, paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}], force=True
    )

    assert [criterion.id for criterion in result.paper] == ["evidence"]
    assert "force=true" in core.audit.read("business")


def test_keeping_a_marked_criterion_is_fine(db, factory, committee, school):
    """The check is about dropped ids, not about editing a rubric that has been used."""
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6})

    result = _replace(db, paper=[{"id": "clarity", "label": "Clarity", "maxScore": 20}])

    assert result.paper[0].maxScore == 20.0


def test_a_refused_awards_save_leaves_the_paper_rubric_alone(db, factory, committee, school):
    """One transaction: a blocked awards rubric must not half-apply the paper one."""
    factory.new_delegate(committee, school, overall_rubric_scores={"speaking": 4})

    with pytest.raises(RubricCriterionInUse):
        _replace(
            db,
            paper=[{"id": "clarity", "label": "Clarity", "maxScore": 10}],
            awards=[{"id": "diplomacy", "label": "Diplomacy", "levels": [{"score": 3, "label": "S"}]}],
        )

    assert rubric_docs.read(db, rubric_docs.PAPER) == []
