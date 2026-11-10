"""The two conference-wide rubrics: the read side.

One JSON document each, stored in `rubrics.items` (see crud.database_schema.Rubric):

    'paper'   flat criteria   {id, label, maxScore}      -> GET /chair/rubric
    'awards'  leveled criteria {id, label, levels[]}      -> GET /chair/awards/rubric

Read through one module so the chair's rubric, the award validation and the delegate's
graded breakdown can never disagree about labels or maxima - the same reason
`build_paper_rubric` and `grade_paper` shared a source before the rubric became editable.

**Falling back to core.controls matters.** A missing row means the rubric was never saved
through the admin API, so the in-code defaults are the answer. That is what a database
bootstrapped before `rubrics` existed looks like, and it is also what keeps a test that
monkeypatches `core.controls.paper_rubric_data` in control of the rubric: the attribute is
read at call time, never copied into a local at import time.

A missing *table* is not covered here - that is a database that needs `crud/seed.py` run
once after deploying, exactly like any other new table.
"""

from sqlalchemy.orm import Session

import core.controls
from crud.database_schema import Rubric
from schemas.response_models import AwardsRubricCriterion, GradingRubricCriterion, RubricLevel

PAPER = "paper"
AWARDS = "awards"
KINDS = (PAPER, AWARDS)


def read(db: Session, kind: str) -> list[dict]:
    """The stored document for one rubric, or the in-code defaults when it was never saved."""
    row = db.get(Rubric, kind)
    if row is None:
        return list(_defaults(kind))
    return list(row.items or [])


def paper_criteria(db: Session) -> list[GradingRubricCriterion]:
    """The paper rubric as the grading view and the delegate breakdown consume it.

    An entry with no `id` is skipped: `id` is the key a mark is stored under, so such an
    entry could never be graded - the delegate-side join skips it for the same reason.
    """
    rubric: list[GradingRubricCriterion] = []
    for criterion in read(db, PAPER):
        criterion_id = criterion.get("id")
        if criterion_id is None:
            continue
        rubric.append(
            GradingRubricCriterion(
                id=criterion_id,
                label=criterion.get("label") or str(criterion_id),
                maxScore=float(criterion.get("maxScore", 0)),
            )
        )
    return rubric


def awards_criteria(db: Session) -> list[AwardsRubricCriterion]:
    """The awards rubric as the awards view and the award validation consume it.

    A criterion with no usable levels is skipped entirely: the view works out each
    criterion's maximum as `Math.max(...levels)`, so an empty list would give it
    -Infinity. A level with no label is skipped for the same reason a label-less checklist
    line is: there would be nothing to render.
    """
    rubric: list[AwardsRubricCriterion] = []

    for criterion in read(db, AWARDS):
        criterion_id = criterion.get("id")
        if criterion_id is None:
            # `id` keys the scores map, so a criterion without one could never be stored.
            continue

        levels: list[RubricLevel] = []
        for level in criterion.get("levels") or []:
            if not isinstance(level, dict):
                continue
            label = str(level.get("label") or "").strip()
            if not label:
                continue
            levels.append(
                RubricLevel(
                    score=float(level.get("score", 0)),
                    label=label,
                    description=str(level.get("description") or ""),
                )
            )

        if not levels:
            continue

        rubric.append(
            AwardsRubricCriterion(
                id=criterion_id,
                label=str(criterion.get("label") or criterion_id),
                levels=levels,
            )
        )

    return rubric


def _defaults(kind: str) -> list[dict]:
    """The pre-database defaults, read from core.controls at call time (see module docstring)."""
    if kind == PAPER:
        return list(core.controls.paper_rubric_data)
    if kind == AWARDS:
        return list(core.controls.awards_rubric)
    return []
