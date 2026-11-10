"""Admin use case for editing the two conference-wide rubrics (§8.11).

The read side lives in `core.domain.rubrics`, because the chair views and the delegate's
graded breakdown need it too. This module is only what *changing* a rubric involves:
validation that depends on the other entries, the database write, and the audit line.

The rule worth understanding before changing anything here: an entry's `id` is the key
every stored mark is filed under (`delegates.paper_rubric_grade` and
`delegates.overall_rubric_scores` are JSONB maps keyed by criterion id). Dropping or
renaming a criterion therefore strands real grading work, so a save that would do it is
refused unless the caller passes `force`.

Values arrive as plain dicts (the endpoint has already validated their shape with
`schemas.request_models`), matching how the other admin use cases take a `model_dump()`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.audit
from core.domain import errors
from core.domain import rubrics
from crud.database_schema import Delegates, Rubric
from crud.db import utcnow
from schemas.response_models import RubricResponse


def _marked_counts(db: Session, kind: str) -> dict[str, int]:
    """How many delegates have a mark filed under each criterion id of one rubric.

    Keys are compared as strings because JSONB object keys always are: a rubric whose ids
    are numbers (which the models allow) would otherwise never match its own stored marks.
    """
    column = (
        Delegates.paper_rubric_grade
        if kind == rubrics.PAPER
        else Delegates.overall_rubric_scores
    )

    counts: dict[str, int] = {}
    for marks in db.scalars(select(column).where(column.is_not(None))).all():
        for criterion_id in marks or {}:
            key = str(criterion_id)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _orphaned(db: Session, kind: str, items: list[dict]) -> dict[str, int]:
    """The marked ids the submitted rubric no longer contains."""
    kept = {str(item["id"]) for item in items}
    return {
        criterion_id: count
        for criterion_id, count in _marked_counts(db, kind).items()
        if criterion_id not in kept
    }


def _validate(kind: str, items: list[dict]) -> None:
    """Refuse a rubric that cannot be graded, with a sentence the admin can act on.

    The request schema has already checked types, lengths, a positive maximum and at least
    one level per criterion. What is left needs the whole list at once, or needs wording
    that names the criterion rather than a JSON path:

    * a repeated `id`, which would make every mark filed under it ambiguous;
    * a blank id or label - an empty heading is unreadable in the grading view;
    * a blank level label, which the awards matrix renders as an empty cell.

    Ids and labels are stripped in place so the stored document is what the editor typed
    rather than what it typed plus spaces.
    """
    seen: set[str] = set()

    for position, item in enumerate(items, start=1):
        for field in ("id", "label"):
            if isinstance(item.get(field), str):
                item[field] = item[field].strip()

        key = str(item["id"])
        if key == "":
            raise errors.RubricInvalid(
                f"criterion {position} of the {kind} rubric needs an id "
                "(it is what every recorded mark is filed under)"
            )
        if key in seen:
            raise errors.RubricInvalid(
                f"the {kind} rubric lists the criterion id '{key}' more than once; "
                "ids are what every recorded mark is filed under"
            )
        seen.add(key)

        if not item["label"]:
            raise errors.RubricInvalid(
                f"criterion '{key}' of the {kind} rubric needs a label "
                "(the grading view prints it above the input)"
            )

        if kind != rubrics.AWARDS:
            continue

        for level_number, level in enumerate(item.get("levels") or [], start=1):
            if isinstance(level.get("label"), str):
                level["label"] = level["label"].strip()
            if not level.get("label"):
                raise errors.RubricInvalid(
                    f"level {level_number} of criterion '{key}' needs a label "
                    "(the awards matrix renders it as the score cell)"
                )


def replace(
    db: Session,
    *,
    paper: list[dict] | None = None,
    awards: list[dict] | None = None,
    actor: str,
    force: bool = False,
) -> RubricResponse:
    """Replace one or both rubrics, and return both as they now stand.

    An omitted rubric is left untouched, so the paper editor and the awards editor cannot
    clobber each other: there is one key per rubric in the body, and `None` means "not
    submitted" while `[]` means "make it empty".

    Refuses with `RubricCriterionInUse` - listing every marked id it would strand - when a
    submitted rubric drops an id that already has marks, unless `force` is set. Everything
    is written in one transaction, so a refused awards rubric cannot leave the paper rubric
    half-updated.
    """
    submitted: dict[str, list[dict]] = {}
    if paper is not None:
        submitted[rubrics.PAPER] = paper
    if awards is not None:
        submitted[rubrics.AWARDS] = awards

    if not submitted:
        raise errors.NothingToUpdate()

    for kind, items in submitted.items():
        _validate(kind, items)

    if not force:
        blocked = {
            kind: orphaned
            for kind, items in submitted.items()
            if (orphaned := _orphaned(db, kind, items))
        }
        if blocked:
            raise errors.RubricCriterionInUse(blocked)

    for kind, items in submitted.items():
        row = db.get(Rubric, kind)
        if row is None:
            db.add(Rubric(kind=kind, items=items, updated_at=utcnow(), updated_by=actor))
        else:
            row.items = items
            row.updated_at = utcnow()
            row.updated_by = actor

    db.commit()

    for kind, items in submitted.items():
        core.audit.business(
            "rubric.saved", actor=actor, kind=kind, criteria=len(items), force=force
        )

    return RubricResponse(
        paper=rubrics.paper_criteria(db),
        awards=rubrics.awards_criteria(db),
    )
