"""Domain tests for the rubric read side: ``core.domain.chairs.build_*_rubric`` and
``core.domain.rubrics``.

The interesting rule is the fallback. A **missing row** means "never saved", so the in-code
defaults in ``core.controls`` are the answer; a row that **exists and is empty** means "the
admin saved nothing", and must not resurrect those defaults. That distinction is invisible
from the outside - both look like an empty rubric in a database you did not create - and it is
the difference between an admin being able to clear the rubric and being unable to.

The rest is defensive parsing: `rubrics.py` is the last line of defence for a JSONB document
that an admin (or a hand-edit) could make any shape at all.
"""

from core import controls
from core.domain import chairs as domain
from core.domain import rubrics


def _ids(rubric):
    return [criterion.id for criterion in rubric]


# --- the paper rubric ------------------------------------------------------------------


def test_the_paper_rubric_falls_back_to_the_in_code_defaults(db, monkeypatch):
    """``core.controls`` is read at call time, which is why monkeypatch works at all."""
    monkeypatch.setattr(
        controls,
        "paper_rubric_data",
        [{"id": "clarity", "label": "Clarity", "maxScore": 10}],
    )

    rubric = domain.build_paper_rubric(db)

    assert [(c.id, c.label, c.maxScore) for c in rubric] == [("clarity", "Clarity", 10.0)]


def test_a_stored_rubric_wins_over_the_defaults(db, factory, monkeypatch):
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": "old", "label": "Old", "maxScore": 1}]
    )
    factory.rubric("paper", [{"id": "new", "label": "New", "maxScore": 7}])

    assert _ids(domain.build_paper_rubric(db)) == ["new"]


def test_a_saved_empty_rubric_does_not_fall_back_to_the_defaults(db, factory, monkeypatch):
    """The difference between "never edited" and "cleared on purpose".

    A missing row falls back; an empty row is an answer, so the chair sees no criteria and
    grading is refused with "the rubric has no criteria configured".
    """
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": "old", "label": "Old", "maxScore": 1}]
    )
    factory.rubric("paper", [])

    assert domain.build_paper_rubric(db) == []


def test_a_criterion_without_an_id_is_skipped(db, factory):
    """The id keys every stored mark, so an id-less criterion could never be graded."""
    factory.rubric(
        "paper",
        [{"label": "No id", "maxScore": 5}, {"id": "kept", "label": "Kept", "maxScore": 3}],
    )

    assert _ids(domain.build_paper_rubric(db)) == ["kept"]


def test_a_criterion_without_a_label_uses_its_id(db, factory):
    """There has to be something to render in the editor's row."""
    factory.rubric("paper", [{"id": "clarity", "maxScore": 5}])

    criterion = domain.build_paper_rubric(db)[0]

    assert criterion.label == "clarity"


def test_a_missing_maximum_becomes_zero(db, factory):
    """Zero, not a parse error: the grading screen clamps its input to ``0..max``."""
    factory.rubric("paper", [{"id": "clarity", "label": "Clarity"}])

    assert domain.build_paper_rubric(db)[0].maxScore == 0.0


def test_the_published_rubric_and_the_builder_agree(db, factory):
    """``grade_paper`` validates against the builder; the view reads the published one.

    If these ever drifted, a chair could be blocked from saving a mark for a criterion the
    screen had just shown them.
    """
    factory.rubric("paper", [{"id": "clarity", "label": "Clarity", "maxScore": 10}])

    assert domain.get_position_paper_grading_rubric(db) == domain.build_paper_rubric(db)


# --- the awards rubric -----------------------------------------------------------------


def test_the_awards_rubric_falls_back_to_the_defaults(db, monkeypatch):
    monkeypatch.setattr(
        controls,
        "awards_rubric",
        [
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": [{"score": 4, "label": "Excellent", "description": "Commanding"}],
            }
        ],
    )

    rubric = domain.build_awards_rubric(db)

    assert [(c.id, c.label) for c in rubric] == [("speaking", "Speaking")]
    assert [(level.score, level.label, level.description) for level in rubric[0].levels] == [
        (4.0, "Excellent", "Commanding")
    ]


def test_levels_keep_their_saved_order(db, factory):
    """The order is what the view renders as score cells, so it is not sorted."""
    factory.rubric(
        "awards",
        [
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": [
                    {"score": 4, "label": "Excellent"},
                    {"score": 2, "label": "Developing"},
                ],
            }
        ],
    )

    levels = domain.build_awards_rubric(db)[0].levels

    assert [(level.score, level.label) for level in levels] == [
        (4.0, "Excellent"),
        (2.0, "Developing"),
    ]


def test_a_level_without_a_label_is_skipped(db, factory):
    factory.rubric(
        "awards",
        [
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": [{"score": 4, "label": "   "}, {"score": 2, "label": "Fine"}],
            }
        ],
    )

    assert [level.label for level in domain.build_awards_rubric(db)[0].levels] == ["Fine"]


def test_a_level_that_is_not_an_object_is_skipped(db, factory):
    """Junk in the JSON document must not crash the awards screen.

    ``levels`` is only shape-checked by the admin endpoint; a hand-edit can put a string in
    the array.
    """
    factory.rubric(
        "awards",
        [
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": ["Excellent", {"score": 2, "label": "Fine"}],
            }
        ],
    )

    assert [level.label for level in domain.build_awards_rubric(db)[0].levels] == ["Fine"]


def test_a_criterion_without_usable_levels_is_skipped(db, factory):
    """The view derives each maximum with ``Math.max(...levels)``, so an empty array is
    ``-Infinity``. Such a criterion must never be published.
    """
    factory.rubric(
        "awards",
        [
            {"id": "empty", "label": "Empty", "levels": []},
            {"id": "all-junk", "label": "Junk", "levels": [{"score": 1, "label": ""}]},
            {"id": "kept", "label": "Kept", "levels": [{"score": 1, "label": "Only"}]},
        ],
    )

    assert _ids(domain.build_awards_rubric(db)) == ["kept"]


# --- the reader itself -----------------------------------------------------------------


def test_an_unknown_kind_reads_as_empty(db):
    """A typo in the kind must not raise, and must not return another rubric's document."""
    assert rubrics.read(db, "nonsense") == []


def test_the_two_kinds_are_read_independently(db, factory):
    """One JSONB row per kind; saving the awards rubric must not disturb the paper one."""
    factory.rubric("paper", [{"id": "clarity", "label": "Clarity", "maxScore": 10}])
    factory.rubric(
        "awards",
        [{"id": "speaking", "label": "Speaking", "levels": [{"score": 4, "label": "Good"}]}],
    )

    assert _ids(domain.build_paper_rubric(db)) == ["clarity"]
    assert _ids(domain.build_awards_rubric(db)) == ["speaking"]
