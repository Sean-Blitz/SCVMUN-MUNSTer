"""Admin use cases for the conference checklist and timeline (§8.7, §8.8).

The two are one module because they are the same kind of thing: conference-wide content the
admin edits once and everyone reads. The per-school checklist *ticks* are the one part that
is not conference-wide, and they live here rather than in schools.py because the labels they
point at are defined here.

Checklist: `conference_checklist` holds the labels every school shares, and
`checklist_progress` holds each school's ticks. Lines are reconciled by id - never deleted
and re-inserted wholesale - because a line's id is what progress rows point at, so a rename
must not silently wipe every school's tick.

Timeline: `timeline_events` is one schedule shared by every committee, stored as points in
time. There is no completion flag - the chair dashboard compares each event's time with the
clock - which is why the API only ever stores and returns times, and why the list is always
sorted ascending: the view uses the next event's time as the end of the current window.
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import core.audit
from core import controls
from core.domain.errors import (
    ChecklistItemNeedsOneIdentifier,
    ChecklistItemNotFound,
    ChecklistItemSentTwice,
    ChecklistLabelMissing,
    ChecklistLabelNotFound,
    ChecklistLabelRepeated,
    ChecklistLabelTooLong,
    PinnedEventRemoved,
    TimelineLabelMissing,
    TimelineLabelTooLong,
    TimelinePhaseInvalid,
    TimelineTimestampAware,
    TooManyChecklistItems,
    TooManyTimelineEvents,
)
from core.domain.admin.schools import require_school_by_id
from crud.database_schema import (
    ChecklistProgress,
    ConferenceChecklist,
    School,
    TimelineEvent,
)
from crud.db import utcnow
from schemas.response_models import (
    ConferenceChecklistItem,
    ConferenceChecklistResponse,
    SchoolChecklistItem,
    SchoolChecklistResponse,
    TimelineEntry,
    TimelineListResponse,
)

MAX_CHECKLIST_ITEMS = 20
MAX_CHECKLIST_LABEL = 200

MAX_TIMELINE_EVENTS = 30
MAX_TIMELINE_LABEL = 200


def _ordered_items(db: Session) -> list[ConferenceChecklist]:
    return list(
        db.scalars(
            select(ConferenceChecklist).order_by(
                ConferenceChecklist.position, ConferenceChecklist.id
            )
        ).all()
    )


def _school_checklist(db: Session, school: School) -> SchoolChecklistResponse:
    """One school's checklist: every shared label, plus that school's tick if it has one."""
    rows = db.execute(
        select(ConferenceChecklist, ChecklistProgress.completed)
        .outerjoin(
            ChecklistProgress,
            (ChecklistProgress.item_id == ConferenceChecklist.id)
            & (ChecklistProgress.school_id == school.account_id),
        )
        .order_by(ConferenceChecklist.position, ConferenceChecklist.id)
    ).all()

    return SchoolChecklistResponse(
        school_id=school.account_id,
        school_name=school.school_name,
        items=[
            SchoolChecklistItem(id=item.id, label=item.label, completed=bool(completed))
            for item, completed in rows
        ],
    )


def get_checklist(db: Session) -> ConferenceChecklistResponse:
    """The shared checklist labels, in display order. Ticks are per school."""
    return ConferenceChecklistResponse(
        items=[
            ConferenceChecklistItem(id=item.id, label=item.label)
            for item in _ordered_items(db)
        ]
    )


def replace_checklist(
    db: Session, *, items: list, actor: str
) -> ConferenceChecklistResponse:
    """Reconcile the shared checklist with the submitted lines, in display order.

    Lines that arrive with an id are updated in place, so their schools' ticks survive;
    lines with no id are created; lines that are absent are deleted, taking their progress
    with them. Labels must be unique (case-insensitively) so a script can address a line by
    name as well as by id.
    """
    if len(items) > MAX_CHECKLIST_ITEMS:
        raise TooManyChecklistItems(MAX_CHECKLIST_ITEMS)

    existing = {item.id: item for item in _ordered_items(db)}

    seen_ids: set[int] = set()
    seen_labels: set[str] = set()
    prepared: list[tuple[ConferenceChecklist | None, str]] = []

    for position, entry in enumerate(items, start=1):
        label = entry.label.strip()
        if not label:
            raise ChecklistLabelMissing(position)
        if len(label) > MAX_CHECKLIST_LABEL:
            raise ChecklistLabelTooLong(position, MAX_CHECKLIST_LABEL)

        folded = label.casefold()
        if folded in seen_labels:
            raise ChecklistLabelRepeated(position, label)
        seen_labels.add(folded)

        row: ConferenceChecklist | None = None
        if entry.id is not None:
            row = existing.get(entry.id)
            if row is None:
                raise ChecklistItemNotFound(entry.id)
            if entry.id in seen_ids:
                raise ChecklistItemSentTwice(entry.id)
            seen_ids.add(entry.id)

        prepared.append((row, label))

    # Update and create in place, then delete whatever the payload left out.
    for position, (row, label) in enumerate(prepared):
        if row is None:
            db.add(ConferenceChecklist(label=label, position=position))
        else:
            row.label = label
            row.position = position

    for item_id, row in existing.items():
        if item_id not in seen_ids:
            db.delete(row)

    db.commit()

    core.audit.business(
        "checklist.updated",
        actor=actor,
        lines=len(prepared),
    )

    return get_checklist(db)


def get_school_checklist(db: Session, school_id: int) -> SchoolChecklistResponse:
    """The shared labels with this school's ticks - what its advisor sees, plus the ids."""
    return _school_checklist(db, require_school_by_id(db, school_id))


def update_school_checklist(
    db: Session, school_id: int, *, items: list, actor: str
) -> SchoolChecklistResponse:
    """Tick or untick lines for one school, addressing each by id or by label.

    A partial update: lines that are not listed keep their current state, which is what makes
    this convenient to call from a script ("mark 'Pay the conference fee' done"). The admin UI
    sends every line, which amounts to a full save. Returns the school's checklist afterwards.
    """
    school = require_school_by_id(db, school_id)
    by_id = {item.id: item for item in _ordered_items(db)}
    by_label = {item.label.casefold(): item for item in by_id.values()}

    resolved: list[tuple[ConferenceChecklist, bool]] = []
    for position, entry in enumerate(items, start=1):
        if (entry.id is None) == (entry.label is None):
            raise ChecklistItemNeedsOneIdentifier(position)

        if entry.id is not None:
            item = by_id.get(entry.id)
            if item is None:
                raise ChecklistItemNotFound(entry.id)
        else:
            item = by_label.get((entry.label or "").strip().casefold())
            if item is None:
                raise ChecklistLabelNotFound(entry.label or "")

        resolved.append((item, bool(entry.completed)))

    # Upsert: the pair (school, item) is the primary key, so a second save updates the row.
    for item, completed in resolved:
        row = db.get(ChecklistProgress, (school.account_id, item.id))
        if row is None:
            db.add(
                ChecklistProgress(
                    school_id=school.account_id,
                    item_id=item.id,
                    completed=completed,
                    updated_at=utcnow(),
                )
            )
        else:
            row.completed = completed
            row.updated_at = utcnow()

    db.commit()

    core.audit.business(
        "checklist.progress",
        actor=actor,
        school=school.school_name,
        ticked=sum(1 for _, completed in resolved if completed),
        cleared=sum(1 for _, completed in resolved if not completed),
    )

    return _school_checklist(db, school)


def _timeline_response(db: Session) -> TimelineListResponse:
    """Every timeline event, earliest first."""
    rows = db.scalars(
        select(TimelineEvent).order_by(TimelineEvent.starts_at, TimelineEvent.id)
    ).all()
    return TimelineListResponse(
        events=[
            TimelineEntry(
                id=row.id,
                phase=row.phase,
                label=row.label,
                starts_at=row.starts_at,
                pinned=row.pinned,
            )
            for row in rows
        ]
    )


def get_timeline(db: Session) -> TimelineListResponse:
    """The conference schedule, earliest first. Empty until an admin fills it in."""
    return _timeline_response(db)


def replace_timeline(db: Session, *, events: list, actor: str) -> TimelineListResponse:
    """Replace the conference schedule with the submitted events.

    Nothing else references an event, so this is a plain delete-then-insert in one
    transaction; the events come back sorted by time, not in the order they were sent.

    The pinned "Conference Start" row is the exception: its time is the conference's start
    and the target of the header countdown, so it can be re-dated but not removed or renamed.
    Because the payload carries no ids - events have no identity to preserve - it is matched
    by (phase, label), which is why the label is part of the rule.
    """
    if len(events) > MAX_TIMELINE_EVENTS:
        raise TooManyTimelineEvents(MAX_TIMELINE_EVENTS)

    pinned_existing = {
        (row.phase, row.label)
        for row in db.scalars(
            select(TimelineEvent).where(TimelineEvent.pinned.is_(True))
        ).all()
    }

    prepared: list[TimelineEvent] = []
    for position, entry in enumerate(events, start=1):
        label = entry.label.strip()
        if not label:
            raise TimelineLabelMissing(position)
        if len(label) > MAX_TIMELINE_LABEL:
            raise TimelineLabelTooLong(position, MAX_TIMELINE_LABEL)
        if entry.phase not in controls.TIMELINE_PHASES:
            raise TimelinePhaseInvalid(position, controls.TIMELINE_PHASES)
        if entry.starts_at.tzinfo is not None:
            # The column is naive UTC; an aware value would land shifted by whatever the
            # database session's offset happens to be.
            raise TimelineTimestampAware(position)

        prepared.append(
            TimelineEvent(
                phase=entry.phase,
                label=label,
                starts_at=entry.starts_at,
                pinned=(entry.phase, label) in pinned_existing,
            )
        )

    # Refuse before deleting anything: a schedule that drops the pinned line would take the
    # conference's start time (and the countdown) with it.
    submitted = {(event.phase, event.label) for event in prepared}
    if pinned_existing - submitted:
        missing = ", ".join(sorted(label for _phase, label in pinned_existing - submitted))
        raise PinnedEventRemoved(missing)

    db.execute(delete(TimelineEvent))
    db.add_all(prepared)
    db.commit()

    core.audit.business(
        "timeline.updated",
        actor=actor,
        events=len(prepared),
    )

    return _timeline_response(db)
