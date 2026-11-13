"""Domain tests for ``core.domain.admin.broadcasts`` (§8.6).

The rule that deserves its own file is the **cap arithmetic**. The dashboard has room for 2
global + 1 committee announcement and 2 global + 3 committee links, and the cap counts only the
rows a delegate can still see:

* no ``ends_at``, or one in the future, holds a slot;
* an expired row frees its slot, which is why a create or edit with a past ``ends_at`` skips
  the check entirely;
* an edit re-checks the *new* target and schedule, while excluding the row being edited - so
  moving a line to a busier committee can be refused, and re-saving a live line cannot count
  itself.

The exceptions carry the kind, the cap and the audience string the endpoint renders.
"""

from datetime import datetime, timedelta

import pytest

import core.audit
from core.domain.admin import broadcasts
from core.domain.errors import (
    AnnouncementHasUrl,
    BroadcastCapReached,
    BroadcastNotFound,
    EmptyBroadcastBody,
    InvalidBroadcastKind,
    InvertedWindow,
    LinkNeedsUrl,
    UnknownCommittee,
)
from crud.database_schema import Broadcast
from crud.db import utcnow

PAST = datetime(2026, 1, 1, 9, 0)
FUTURE = utcnow() + timedelta(days=30)


def _create(db, **kwargs):
    defaults = dict(
        kind="announcement",
        body="Notice",
        url=None,
        committee_name=None,
        position=0,
        starts_at=None,
        ends_at=None,
        actor="admin:1",
    )
    defaults.update(kwargs)
    return broadcasts.create_broadcast(db, **defaults)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_an_unknown_kind_lists_the_supported_ones(db):
    with pytest.raises(InvalidBroadcastKind) as raised:
        _create(db, kind="headline")

    assert raised.value.kinds == ("announcement", "link")


def test_an_empty_body_is_refused(db):
    with pytest.raises(EmptyBroadcastBody):
        _create(db, body="   ")


def test_a_link_needs_a_url(db):
    with pytest.raises(LinkNeedsUrl):
        _create(db, kind="link", body="Handbook")


def test_an_announcement_cannot_carry_a_url(db):
    with pytest.raises(AnnouncementHasUrl):
        _create(db, url="https://example.test")


def test_an_unknown_committee_is_refused(db):
    with pytest.raises(UnknownCommittee) as raised:
        _create(db, committee_name="NONEXISTENT")

    assert raised.value.committee_name == "NONEXISTENT"


def test_the_body_and_url_are_trimmed(db):
    entry = _create(db, kind="link", body="  Handbook  ", url="  https://example.test/hb  ")

    assert entry.body == "Handbook"
    assert entry.url == "https://example.test/hb"


def test_an_inverted_window_is_refused(db):
    with pytest.raises(InvertedWindow):
        _create(db, starts_at=FUTURE, ends_at=PAST)


# ---------------------------------------------------------------------------
# The caps
# ---------------------------------------------------------------------------


def test_the_global_announcement_cap_is_two(db):
    _create(db, body="One")
    _create(db, body="Two")

    with pytest.raises(BroadcastCapReached) as raised:
        _create(db, body="Three")

    assert (raised.value.kind, raised.value.cap) == ("announcement", 2)
    assert raised.value.audience == "for every delegate"


def test_the_committee_announcement_cap_is_one(db, committee):
    _create(db, body="Committee line", committee_name="DISEC")

    with pytest.raises(BroadcastCapReached) as raised:
        _create(db, body="Another", committee_name="DISEC")

    assert raised.value.cap == 1
    assert raised.value.audience == "for DISEC"


def test_the_link_caps_differ_from_the_announcement_caps(db, committee):
    """Links get 2 global and 3 per committee; announcements get 2 and 1."""
    _create(db, kind="link", body="One", url="https://example.test/1")
    _create(db, kind="link", body="Two", url="https://example.test/2")

    with pytest.raises(BroadcastCapReached):
        _create(db, kind="link", body="Three", url="https://example.test/3")

    for index in range(3):
        _create(
            db,
            kind="link",
            body=f"Committee {index}",
            url=f"https://example.test/c{index}",
            committee_name="DISEC",
        )

    with pytest.raises(BroadcastCapReached):
        _create(
            db,
            kind="link",
            body="Committee three",
            url="https://example.test/c3",
            committee_name="DISEC",
        )


def test_an_expired_line_frees_its_slot(db):
    """The cap bounds what a delegate can see, so history does not hold a slot."""
    for index in range(3):
        _create(
            db,
            body=f"Old {index}",
            starts_at=PAST,
            ends_at=PAST + timedelta(hours=1),
        )

    # Two live slots are still free.
    _create(db, body="Live one")
    _create(db, body="Live two")


def test_a_line_that_ends_later_still_holds_its_slot(db):
    """Scheduled-but-not-started counts: a delegate will see it."""
    _create(db, body="One")
    _create(db, body="Two", starts_at=FUTURE, ends_at=FUTURE + timedelta(days=1))

    with pytest.raises(BroadcastCapReached):
        _create(db, body="Three")


# ---------------------------------------------------------------------------
# update_broadcast
# ---------------------------------------------------------------------------


def test_an_edit_applies_only_what_is_given(db):
    created = _create(db, body="Original", position=3)

    entry = broadcasts.update_broadcast(
        db, created.id, changes={"body": "Corrected"}, actor="admin:1"
    )

    assert entry.body == "Corrected"
    assert entry.position == 3
    assert entry.kind == "announcement"


def test_the_kind_cannot_be_changed(db):
    """Moving a line between strips is a delete + create; ``kind`` is not in the change set."""
    created = _create(db, body="Notice")

    entry = broadcasts.update_broadcast(
        db, created.id, changes={"kind": "link"}, actor="admin:1"
    )

    assert entry.kind == "announcement"


def test_editing_re_checks_the_new_target(db, committee):
    _create(db, body="Committee line", committee_name="DISEC")
    elsewhere = _create(db, body="Global line")

    with pytest.raises(BroadcastCapReached):
        broadcasts.update_broadcast(
            db, elsewhere.id, changes={"committee_name": "DISEC"}, actor="admin:1"
        )


def test_editing_a_live_line_does_not_count_itself(db):
    """The row being edited is excluded from the count, or a no-op save would fail."""
    created = _create(db, body="One")
    _create(db, body="Two")

    entry = broadcasts.update_broadcast(
        db, created.id, changes={"body": "One, corrected"}, actor="admin:1"
    )

    assert entry.body == "One, corrected"


def test_reviving_an_expired_line_re_checks_the_cap(db):
    old = _create(db, body="Old", starts_at=PAST, ends_at=PAST + timedelta(hours=1))
    _create(db, body="Live one")
    _create(db, body="Live two")

    with pytest.raises(BroadcastCapReached):
        broadcasts.update_broadcast(db, old.id, changes={"ends_at": None}, actor="admin:1")


def test_editing_an_unknown_broadcast_is_refused(db):
    with pytest.raises(BroadcastNotFound) as raised:
        broadcasts.update_broadcast(db, 999_999, changes={"body": "x"}, actor="admin:1")

    assert raised.value.broadcast_id == 999_999


# ---------------------------------------------------------------------------
# list_broadcasts / delete_broadcast
# ---------------------------------------------------------------------------


def test_the_editor_list_includes_expired_lines_and_orders_by_position(db):
    """Expired rows are kept - they are the admin's only way to clean up - and positions order."""
    _create(db, body="Expired", position=2, starts_at=PAST, ends_at=PAST + timedelta(hours=1))
    _create(db, body="Live", position=1)

    entries = broadcasts.list_broadcasts(db).broadcasts

    assert [entry.body for entry in entries] == ["Live", "Expired"]


def test_the_list_can_be_filtered_by_kind(db):
    _create(db, body="Notice")
    _create(db, kind="link", body="Handbook", url="https://example.test/hb")

    entries = broadcasts.list_broadcasts(db, kind="link").broadcasts

    assert [entry.kind for entry in entries] == ["link"]


def test_an_unknown_filter_kind_is_refused(db):
    with pytest.raises(InvalidBroadcastKind):
        broadcasts.list_broadcasts(db, kind="headline")


def test_deleting_removes_the_row_and_is_audited(db):
    created = _create(db, body="Gone")
    before = core.audit.read("business")

    broadcasts.delete_broadcast(db, created.id, actor="admin:1")

    assert db.get(Broadcast, created.id) is None
    assert "broadcast.withdrawn" in core.audit.read("business")[len(before):]


def test_deleting_an_unknown_broadcast_is_refused(db):
    with pytest.raises(BroadcastNotFound):
        broadcasts.delete_broadcast(db, 999_999, actor="admin:1")
