"""Domain tests for ``core.domain.admin.committees`` (§8.10).

A committee's name is its primary key and three tables reference it without a cascade-on-update,
so ``update_committee`` is a transaction rather than a column write: insert the new row, repoint
``delegates``, ``chairs`` and ``broadcasts``, then remove the old one. A failure anywhere leaves
the old name and its children intact - which is what most of this file is about.

The exceptions carry the names the endpoints put into their messages, so the attributes are
asserted rather than the ``str()``.
"""

import pytest
from sqlalchemy import select

import core.audit
from core.domain.admin import committees
from core.domain.errors import (
    BlankField,
    ChairNotInCommittee,
    CommitteeExists,
    DelegateNotInCommittee,
    NoChanges,
    UnknownCommittee,
)
from crud.database_schema import Account, Broadcast, Chairs, Committees, Delegates, School


# ---------------------------------------------------------------------------
# Lookup and list
# ---------------------------------------------------------------------------


def test_an_unknown_name_carries_the_name(db):
    with pytest.raises(UnknownCommittee) as raised:
        committees.require_committee(db, "NONEXISTENT")

    assert raised.value.committee_name == "NONEXISTENT"


def test_the_list_is_the_names(db, factory):
    factory.committee("UNSC")
    factory.committee("DISEC")

    assert set(committees.list_committees(db)) == {"DISEC", "UNSC"}


def test_the_detail_lists_chairs_and_delegates(db, factory, committee, school):
    """A committee spans schools, so each delegate carries its own school's name."""
    chair = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )
    delegate = factory.new_delegate(committee, school, country="France")

    detail = committees.get_committee_detail(db, "DISEC")

    assert [(entry.account_id, entry.name, entry.hash) for entry in detail.chairs] == [
        (chair.account_id, "Chair Person", chair.hash)
    ]
    (entry,) = detail.delegates
    assert entry.account_id == delegate.account_id
    assert entry.school_name == "Test High School"
    assert entry.country == "France"
    assert entry.paper_status == "unsubmitted"
    assert entry.has_paper is False


# ---------------------------------------------------------------------------
# create_committee
# ---------------------------------------------------------------------------


def test_a_name_is_enough(db):
    detail = committees.create_committee(
        db, name="UNSC", committee_type=None, topic=None, actor="admin:1"
    )

    assert detail.committee_name == "UNSC"
    assert detail.committee_type is None
    assert detail.topic is None


def test_a_duplicate_name_is_refused(db):
    committees.create_committee(db, name="UNSC", committee_type=None, topic=None, actor="admin:1")

    with pytest.raises(CommitteeExists) as raised:
        committees.create_committee(
            db, name="UNSC", committee_type=None, topic=None, actor="admin:1"
        )

    assert raised.value.committee_name == "UNSC"


def test_a_blank_name_is_refused(db):
    with pytest.raises(BlankField) as raised:
        committees.create_committee(
            db, name="   ", committee_type=None, topic=None, actor="admin:1"
        )

    assert raised.value.field == "committee_name"


def test_creation_is_audited(db):
    before = core.audit.read("technical")

    committees.create_committee(
        db, name="UNSC", committee_type=None, topic=None, actor="admin:1"
    )

    assert "committee.created" in core.audit.read("technical")[len(before):]


# ---------------------------------------------------------------------------
# update_committee
# ---------------------------------------------------------------------------


def test_type_and_topic_can_be_set_and_cleared(db, committee):
    detail = committees.update_committee(
        db,
        "DISEC",
        changes={"committee_type": "General Assembly", "topic": "Cyber norms"},
        actor="admin:1",
    )
    assert (detail.committee_type, detail.topic) == ("General Assembly", "Cyber norms")

    cleared = committees.update_committee(
        db, "DISEC", changes={"committee_type": None, "topic": None}, actor="admin:1"
    )
    assert (cleared.committee_type, cleared.topic) == (None, None)


def test_an_empty_change_set_is_refused(db, committee):
    with pytest.raises(NoChanges):
        committees.update_committee(db, "DISEC", changes={}, actor="admin:1")


def test_renaming_repoints_every_child(db, factory, committee, school):
    """Three tables reference the name by value and none cascades on update."""
    chair = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )
    delegate = factory.new_delegate(committee, school, country="France")
    factory.broadcast(body="For DISEC", committee=committee)

    detail = committees.update_committee(
        db, "DISEC", changes={"committee_name": "DISEC II"}, actor="admin:1"
    )

    assert detail.committee_name == "DISEC II"
    db.expire_all()
    assert db.get(Delegates, delegate.account_id).committee == "DISEC II"
    assert db.get(Chairs, chair.account_id).committee_name == "DISEC II"
    assert db.scalars(select(Broadcast)).one().committee_name == "DISEC II"
    # The old row is gone, not left behind.
    assert db.get(Committees, "DISEC") is None


def test_renaming_onto_a_taken_name_is_refused(db, factory, committee):
    factory.committee("UNSC")

    with pytest.raises(CommitteeExists):
        committees.update_committee(
            db, "DISEC", changes={"committee_name": "UNSC"}, actor="admin:1"
        )


def test_renaming_to_a_blank_name_is_refused(db, committee):
    with pytest.raises(BlankField) as raised:
        committees.update_committee(
            db, "DISEC", changes={"committee_name": "  "}, actor="admin:1"
        )

    assert raised.value.field == "committee_name"


def test_a_refused_rename_leaves_the_children_alone(db, factory, committee, school):
    """One transaction: the repoint cannot half-happen."""
    factory.committee("UNSC")
    delegate = factory.new_delegate(committee, school, country="France")

    with pytest.raises(CommitteeExists):
        committees.update_committee(
            db, "DISEC", changes={"committee_name": "UNSC"}, actor="admin:1"
        )

    db.expire_all()
    assert db.get(Delegates, delegate.account_id).committee == "DISEC"


# ---------------------------------------------------------------------------
# Chairs
# ---------------------------------------------------------------------------


def test_a_chair_is_created_claimable(db, committee):
    """Nothing else creates a ``chairs`` row, so this is the only way in."""
    entry = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )

    assert entry.name == "Chair Person"
    assert len(entry.hash) == 16

    account = db.get(Account, entry.account_id)
    assert account.role == "chair"
    assert account.identifier == entry.hash
    assert account.password_hash is None


def test_a_chair_can_be_updated(db, committee):
    entry = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )

    updated = committees.update_committee_chair(
        db, "DISEC", entry.account_id, changes={"email": "new@example.test"}, actor="admin:1"
    )

    assert updated.email == "new@example.test"
    assert updated.name == "Chair Person"


def test_an_empty_chair_edit_is_refused(db, committee):
    entry = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )

    with pytest.raises(NoChanges):
        committees.update_committee_chair(
            db, "DISEC", entry.account_id, changes={}, actor="admin:1"
        )


def test_a_chair_of_another_committee_is_refused(db, factory, committee):
    factory.committee("UNSC")
    entry = committees.create_committee_chair(
        db, "UNSC", name="Other Chair", email="other@example.test", actor="admin:1"
    )

    with pytest.raises(ChairNotInCommittee):
        committees.update_committee_chair(
            db, "DISEC", entry.account_id, changes={"name": "Renamed"}, actor="admin:1"
        )

    with pytest.raises(ChairNotInCommittee):
        committees.delete_committee_chair(db, "DISEC", entry.account_id, actor="admin:1")


def test_deleting_a_chair_removes_the_profile_and_the_account(db, committee):
    entry = committees.create_committee_chair(
        db, "DISEC", name="Chair Person", email="chair@example.test", actor="admin:1"
    )

    committees.delete_committee_chair(db, "DISEC", entry.account_id, actor="admin:1")

    assert db.get(Chairs, entry.account_id) is None
    assert db.get(Account, entry.account_id) is None


# ---------------------------------------------------------------------------
# Removing a delegate
# ---------------------------------------------------------------------------


def test_removing_a_delegate_takes_their_rows_and_their_paper(
    db, factory, committee, school, papers_dir
):
    delegate = factory.new_delegate(committee, school, country="France")
    factory.upload(delegate, file_path="paper.pdf", write_bytes=b"%PDF-paper")
    account_id = delegate.account_id

    result = committees.delete_committee_delegate(
        db, "DISEC", account_id, actor="admin:1"
    )

    assert (result.delegate, result.school, result.files_deleted) == (
        "France",
        "Test High School",
        1,
    )
    assert db.scalars(select(Delegates).where(Delegates.account_id == account_id)).first() is None
    assert db.scalars(select(Account).where(Account.id == account_id)).first() is None
    assert not (papers_dir / "paper.pdf").exists()


def test_a_delegate_of_another_committee_is_refused(db, factory, committee, school):
    unsc = factory.committee("UNSC")
    foreign = factory.new_delegate(unsc, school, country="Italy")

    with pytest.raises(DelegateNotInCommittee):
        committees.delete_committee_delegate(
            db, "DISEC", foreign.account_id, actor="admin:1"
        )


def test_the_school_row_survives_removing_one_delegate(db, factory, committee, school):
    """Removing a delegate is not removing a school; the advisor's row is untouched."""
    delegate = factory.new_delegate(committee, school, country="France")

    committees.delete_committee_delegate(db, "DISEC", delegate.account_id, actor="admin:1")

    assert db.get(School, school.account_id) is not None
