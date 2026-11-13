"""Domain tests for ``core.domain.admin.schedule`` (§8.7, §8.8): checklist and timeline.

Both are conference-wide content the admin edits once and everyone reads, and both are
*replaced* by the request rather than patched - but the checklist is **reconciled by id**,
because a line's id is what every school's progress row points at. That is what lets a rename
keep its ticks and an omitted line delete them.

The timeline has no identities at all except the pinned "Conference Start": it is matched by
``(phase, label)``, may be re-dated, and must not be removed or renamed.

The exceptions carry positions, labels and limits, which is how the endpoints build sentences
like "Item 2 repeats the label 'x'."
"""

from datetime import datetime

import pytest

import core.audit
from core.domain.admin import schedule
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
    UnknownSchoolId,
)
from sqlalchemy import select

from crud.database_schema import (
    ChecklistProgress,
    ConferenceChecklist,
    TimelineEvent,
)


class _Item:
    """Stands in for ``ChecklistItemRequest``, which is what the endpoint passes."""

    def __init__(self, label, id=None):
        self.label = label
        self.id = id


class _Progress:
    """Stands in for ``ChecklistProgressUpdate``."""

    def __init__(self, *, completed, id=None, label=None):
        self.completed = completed
        self.id = id
        self.label = label


class _Event:
    """Stands in for ``TimelineEventRequest``."""

    def __init__(self, label, phase="preConference", starts_at=datetime(2026, 12, 1, 9, 0)):
        self.label = label
        self.phase = phase
        self.starts_at = starts_at


# ---------------------------------------------------------------------------
# Checklist labels
# ---------------------------------------------------------------------------


def test_labels_are_created_in_order(db):
    result = schedule.replace_checklist(
        db, items=[_Item("Submit papers"), _Item("Pay the fee")], actor="admin:1"
    )

    assert [item.label for item in result.items] == ["Submit papers", "Pay the fee"]
    assert all(item.id > 0 for item in result.items)


def test_a_listed_id_is_updated_in_place_and_keeps_its_ticks(db, factory, school):
    """The id is the key progress rows point at, so a rename must not replace it."""
    first = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]
    factory.db.add(
        ChecklistProgress(school_id=school.account_id, item_id=first.id, completed=True)
    )
    factory.db.commit()

    result = schedule.replace_checklist(
        db, items=[_Item("Pay the conference fee", id=first.id)], actor="admin:1"
    )

    assert [(item.id, item.label) for item in result.items] == [
        (first.id, "Pay the conference fee")
    ]
    assert db.get(ChecklistProgress, (school.account_id, first.id)).completed is True


def test_a_line_that_is_absent_is_deleted_with_its_ticks(db, factory, school):
    items = schedule.replace_checklist(
        db, items=[_Item("Pay the fee"), _Item("Book travel")], actor="admin:1"
    ).items
    factory.db.add(
        ChecklistProgress(school_id=school.account_id, item_id=items[0].id, completed=True)
    )
    factory.db.commit()

    result = schedule.replace_checklist(
        db, items=[_Item("Book travel", id=items[1].id)], actor="admin:1"
    )

    assert [item.label for item in result.items] == ["Book travel"]
    assert db.get(ConferenceChecklist, items[0].id) is None
    assert db.get(ChecklistProgress, (school.account_id, items[0].id)) is None


def test_a_blank_label_names_its_position(db):
    with pytest.raises(ChecklistLabelMissing) as raised:
        schedule.replace_checklist(
            db, items=[_Item("Fine"), _Item("   ")], actor="admin:1"
        )

    assert raised.value.position == 2


def test_a_repeated_label_names_the_position_and_the_label(db):
    with pytest.raises(ChecklistLabelRepeated) as raised:
        schedule.replace_checklist(
            db, items=[_Item("Pay the fee"), _Item("pay the FEE")], actor="admin:1"
        )

    assert raised.value.position == 2
    assert raised.value.label == "pay the FEE"


def test_an_over_long_label_carries_the_limit(db):
    with pytest.raises(ChecklistLabelTooLong) as raised:
        schedule.replace_checklist(
            db, items=[_Item("x" * 201)], actor="admin:1"
        )

    assert raised.value.limit == 200


def test_the_checklist_has_a_cap(db):
    with pytest.raises(TooManyChecklistItems) as raised:
        schedule.replace_checklist(
            db, items=[_Item(f"Line {n}") for n in range(21)], actor="admin:1"
        )

    assert raised.value.limit == 20


def test_get_checklist_returns_labels_only(db):
    schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1")

    assert [item.label for item in schedule.get_checklist(db).items] == ["Pay the fee"]


# ---------------------------------------------------------------------------
# Per-school ticks
# ---------------------------------------------------------------------------


def test_a_school_checklist_joins_labels_with_its_ticks(db, factory, school):
    line = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]

    before = schedule.get_school_checklist(db, school.account_id)
    assert before.school_name == "Test High School"
    assert [(item.label, item.completed) for item in before.items] == [("Pay the fee", False)]

    schedule.update_school_checklist(
        db, school.account_id, items=[_Progress(id=line.id, completed=True)], actor="admin:1"
    )

    after = schedule.get_school_checklist(db, school.account_id)
    assert after.items[0].completed is True


def test_a_tick_can_address_a_line_by_label(db, school):
    schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1")

    schedule.update_school_checklist(
        db,
        school.account_id,
        items=[_Progress(label="Pay the fee", completed=True)],
        actor="admin:1",
    )

    assert schedule.get_school_checklist(db, school.account_id).items[0].completed is True


def test_lines_that_are_not_listed_keep_their_state(db, school):
    items = schedule.replace_checklist(
        db, items=[_Item("Pay the fee"), _Item("Book travel")], actor="admin:1"
    ).items
    schedule.update_school_checklist(
        db, school.account_id, items=[_Progress(id=items[0].id, completed=True)], actor="admin:1"
    )

    schedule.update_school_checklist(
        db, school.account_id, items=[_Progress(id=items[1].id, completed=True)], actor="admin:1"
    )

    states = schedule.get_school_checklist(db, school.account_id).items
    assert [item.completed for item in states] == [True, True]


def test_addressing_a_line_both_ways_is_refused(db, school):
    """Ambiguity is refused rather than resolved: the two could disagree."""
    line = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]

    with pytest.raises(ChecklistItemNeedsOneIdentifier) as raised:
        schedule.update_school_checklist(
            db,
            school.account_id,
            items=[_Progress(id=line.id, label="Pay the fee", completed=True)],
            actor="admin:1",
        )

    assert raised.value.position == 1


def test_addressing_a_line_neither_way_is_refused(db, school):
    """``{completed: true}`` alone would mean "tick everything" - which is a bulk call."""
    with pytest.raises(ChecklistItemNeedsOneIdentifier):
        schedule.update_school_checklist(
            db, school.account_id, items=[_Progress(completed=True)], actor="admin:1"
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN BUG: _resolve_progress_items does not reject the same line sent twice, so the "
        "duplicate reaches the (school, item) primary key and raises IntegrityError - a 500 "
        "over HTTP. ChecklistItemSentTwice already exists and _schedule_error maps it, but "
        "only replace_checklist raises it. Affects the bulk route too, which shares the helper."
    ),
)
def test_the_same_line_twice_is_refused(db, school):
    """A malformed payload is a 400, not a crash: the other checklist paths already say so."""
    line = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]

    with pytest.raises(ChecklistItemSentTwice) as raised:
        schedule.update_school_checklist(
            db,
            school.account_id,
            items=[_Progress(id=line.id, completed=True), _Progress(id=line.id, completed=False)],
            actor="admin:1",
        )

    assert raised.value.item_id == line.id


def test_an_unknown_line_id_carries_the_id(db, school):
    with pytest.raises(ChecklistItemNotFound) as raised:
        schedule.update_school_checklist(
            db, school.account_id, items=[_Progress(id=999_999, completed=True)], actor="admin:1"
        )

    assert raised.value.item_id == 999_999


def test_an_unknown_label_carries_the_label(db, school):
    with pytest.raises(ChecklistLabelNotFound) as raised:
        schedule.update_school_checklist(
            db,
            school.account_id,
            items=[_Progress(label="No such line", completed=True)],
            actor="admin:1",
        )

    assert raised.value.label == "No such line"


def test_an_unknown_school_carries_the_id(db):
    with pytest.raises(UnknownSchoolId) as raised:
        schedule.get_school_checklist(db, 999_999)

    assert raised.value.school_id == 999_999


def test_a_bulk_tick_reaches_every_school_when_no_ids_are_given(db, factory, school):
    rival = factory.account(role="advisor", name="Rival Advisor")
    rival_school = factory.school(rival, name="Rival High")
    line = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]

    result = schedule.update_checklists_bulk(
        db, school_ids=None, items=[_Progress(id=line.id, completed=True)], actor="admin:1"
    )

    assert (result.schools, result.lines) == (2, 1)
    assert schedule.get_school_checklist(db, rival_school.account_id).items[0].completed is True


def test_a_bulk_tick_with_a_bad_id_writes_nothing(db, factory, school):
    """One transaction: a rejected call must not leave some schools ticked."""
    line = schedule.replace_checklist(db, items=[_Item("Pay the fee")], actor="admin:1").items[0]

    with pytest.raises(UnknownSchoolId):
        schedule.update_checklists_bulk(
            db,
            school_ids=[school.account_id, 999_999],
            items=[_Progress(id=line.id, completed=True)],
            actor="admin:1",
        )

    assert db.get(ChecklistProgress, (school.account_id, line.id)) is None


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def test_the_timeline_is_replaced_and_sorted(db):
    result = schedule.replace_timeline(
        db,
        events=[
            _Event("Second", starts_at=datetime(2027, 1, 1, 9, 0)),
            _Event("Conference", phase="duringConference", starts_at=datetime(2027, 2, 1)),
            _Event("First", starts_at=datetime(2026, 12, 1, 9, 0)),
        ],
        actor="admin:1",
    )

    assert [event.label for event in result.events] == ["First", "Second", "Conference"]
    assert [event.pinned for event in result.events] == [False, False, False]


def test_the_pinned_event_can_be_re_dated_and_stays_pinned(db):
    """Re-dating is how the header countdown is set, so it must be allowed."""
    db.add(
        TimelineEvent(
            phase="preConference",
            label="Conference Start",
            starts_at=datetime(2027, 1, 30),
            pinned=True,
        )
    )
    db.commit()

    result = schedule.replace_timeline(
        db, events=[_Event("Conference Start", starts_at=datetime(2027, 2, 15))], actor="admin:1"
    )

    (event,) = result.events
    assert event.pinned is True
    assert event.starts_at == datetime(2027, 2, 15)


@pytest.mark.parametrize(
    "events",
    [
        [_Event("Something else")],
        [_Event("Opening Ceremony")],  # a rename looks exactly like a removal
        [],
    ],
    ids=["removed", "renamed", "empty"],
)
def test_the_pinned_event_cannot_be_removed_or_renamed(db, events):
    db.add(
        TimelineEvent(
            phase="preConference",
            label="Conference Start",
            starts_at=datetime(2027, 1, 30),
            pinned=True,
        )
    )
    db.commit()

    with pytest.raises(PinnedEventRemoved) as raised:
        schedule.replace_timeline(db, events=events, actor="admin:1")

    assert raised.value.label == "Conference Start"


def test_a_refused_replacement_leaves_the_old_schedule_intact(db):
    """Refuse before deleting: a half-applied schedule would lose the countdown."""
    db.add(
        TimelineEvent(
            phase="preConference",
            label="Conference Start",
            starts_at=datetime(2027, 1, 30),
            pinned=True,
        )
    )
    db.commit()

    with pytest.raises(PinnedEventRemoved):
        schedule.replace_timeline(db, events=[_Event("Something else")], actor="admin:1")

    assert [event.label for event in schedule.get_timeline(db).events] == ["Conference Start"]


def test_a_blank_label_names_its_position(db):
    with pytest.raises(TimelineLabelMissing) as raised:
        schedule.replace_timeline(db, events=[_Event("  ")], actor="admin:1")

    assert raised.value.position == 1


def test_an_over_long_label_carries_the_limit(db):
    with pytest.raises(TimelineLabelTooLong) as raised:
        schedule.replace_timeline(db, events=[_Event("x" * 201)], actor="admin:1")

    assert raised.value.limit == 200


def test_an_invalid_phase_carries_the_allowed_phases(db):
    with pytest.raises(TimelinePhaseInvalid) as raised:
        schedule.replace_timeline(db, events=[_Event("X", phase="intermission")], actor="admin:1")

    assert raised.value.phases == ("preConference", "duringConference")


def test_an_aware_timestamp_is_refused(db):
    """The column is naive UTC; an aware value would land shifted by the session's offset."""
    aware = datetime(2027, 1, 1, tzinfo=datetime.now().astimezone().tzinfo)

    with pytest.raises(TimelineTimestampAware) as raised:
        schedule.replace_timeline(db, events=[_Event("X", starts_at=aware)], actor="admin:1")

    assert raised.value.position == 1


def test_the_timeline_has_a_cap(db):
    with pytest.raises(TooManyTimelineEvents) as raised:
        schedule.replace_timeline(
            db, events=[_Event(f"Event {n}") for n in range(31)], actor="admin:1"
        )

    assert raised.value.limit == 30


def test_replacing_the_timeline_is_audited(db):
    before = core.audit.read("business")

    schedule.replace_timeline(db, events=[_Event("One")], actor="admin:1")

    assert "timeline.updated" in core.audit.read("business")[len(before):]


def test_an_empty_timeline_is_allowed(db):
    assert schedule.get_timeline(db).events == []
    assert schedule.replace_timeline(db, events=[], actor="admin:1").events == []


def test_a_replacement_is_wholesale(db):
    schedule.replace_timeline(
        db, events=[_Event("Old one"), _Event("Old two", starts_at=datetime(2026, 12, 2))],
        actor="admin:1",
    )

    result = schedule.replace_timeline(db, events=[_Event("Only this")], actor="admin:1")

    assert [event.label for event in result.events] == ["Only this"]
    assert len(db.scalars(select(TimelineEvent)).all()) == 1
