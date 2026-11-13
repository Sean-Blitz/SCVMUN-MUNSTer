"""Domain tests for ``core.domain.admin.schools`` (§8.7, §8.9).

Two rules here are only visible below the HTTP layer:

* ``create_school`` builds the advisor *and* the school, because ``schools.account_id`` is the
  advisor's account id - a school cannot exist without one;
* renaming must rewrite the delegate labels stored in ``accounts.name`` ("<school> - #<key>"),
  and must refuse rather than let Postgres truncate a label that would exceed 100 characters.

The exceptions carry the field name, the options or the counts the endpoints render, so the
attributes are asserted rather than the message text.
"""

import pytest
from sqlalchemy import select

import core.audit
import core.security
from core.domain.admin import schools
from core.domain.errors import (
    BlankField,
    ConfirmationMismatch,
    DelegateLabelsTooLong,
    DelegateNotInSchool,
    DelegatePairTaken,
    InvalidPaymentStatus,
    MissingSchoolFields,
    NoChanges,
    SchoolExists,
    UnknownCommittee,
    UnknownSchool,
    UnknownSchoolId,
)
from crud.database_schema import Account, Delegates, School


def _values(name="Lincoln High", **overrides):
    values = {
        "school_name": name,
        "school_address": "1 Test Way",
        "city": "Testville",
        "state": "CA",
        "zip_code": "90000",
        "advisor_name": "Advisor Person",
        "advisor_phone": "555-0100",
        "advisor_email": "advisor@example.test",
        "head_delegate_name": "Head Delegate",
        "head_delegate_email": "head@example.test",
        "head_delegate_phone": "555-0101",
        "payment_status": "unpaid",
        "invoiceURL": None,
    }
    values.update(overrides)
    return values


def _create(db, name="Lincoln High", **overrides):
    return schools.create_school(db, values=_values(name, **overrides), actor="admin:1")


# ---------------------------------------------------------------------------
# create_school
# ---------------------------------------------------------------------------


def test_creating_a_school_creates_its_unclaimed_advisor(db):
    entry = _create(db)

    assert entry.name == "Lincoln High"
    assert len(entry.advisor_hash) == 16

    advisor = db.get(Account, entry.id)
    assert advisor.role == "advisor"
    assert advisor.identifier == entry.advisor_hash
    assert advisor.password_hash is None

    school = db.get(School, entry.id)
    assert school.school_name == "Lincoln High"
    assert school.payment_status == "unpaid"
    assert school.invoiceURL is None


def test_every_missing_field_is_reported_in_a_stable_order(db):
    """The endpoint joins these into one sentence, so the list is the contract."""
    values = _values()
    del values["advisor_phone"]
    values["city"] = "   "

    with pytest.raises(MissingSchoolFields) as raised:
        schools.create_school(db, values=values, actor="admin:1")

    assert raised.value.fields == ("city", "advisor_phone")


def test_an_invalid_payment_status_carries_the_options(db):
    with pytest.raises(InvalidPaymentStatus) as raised:
        _create(db, payment_status="half paid")

    assert raised.value.options == ("paid", "partially paid", "unpaid")


def test_a_duplicate_name_is_refused(db):
    _create(db)

    with pytest.raises(SchoolExists) as raised:
        _create(db, name="Lincoln High")

    assert raised.value.school_name == "Lincoln High"


def test_creation_is_audited(db):
    before = core.audit.read("technical")

    _create(db, name="Audited High")

    assert 'school="Audited High"' in core.audit.read("technical")[len(before):]


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def test_an_unknown_name_carries_the_name(db):
    with pytest.raises(UnknownSchool) as raised:
        schools.require_school(db, "Nowhere High")

    assert raised.value.school_name == "Nowhere High"


def test_an_unknown_id_carries_the_id(db):
    """The views address schools by id and the hash tooling by name; both are real keys."""
    with pytest.raises(UnknownSchoolId) as raised:
        schools.require_school_by_id(db, 999_999)

    assert raised.value.school_id == 999_999


def test_the_list_is_ordered_by_name_with_the_advisor_hash(db, factory):
    for name in ("Rival High", "Lincoln High"):
        advisor = factory.account(role="advisor", name=f"Advisor {name}")
        factory.school(advisor, name=name)

    entries = schools.list_schools(db).schools

    assert [entry.name for entry in entries] == ["Lincoln High", "Rival High"]
    assert all(entry.advisor_hash for entry in entries)


# ---------------------------------------------------------------------------
# update_school
# ---------------------------------------------------------------------------


def test_an_update_applies_only_the_fields_it_is_given(db):
    created = _create(db)

    detail = schools.update_school(db, created.id, changes={"city": "Newville"}, actor="admin:1")

    assert detail.school.city == "Newville"
    assert detail.school.state == "CA"
    assert detail.school.advisor_email == "advisor@example.test"


def test_an_empty_change_set_is_refused(db):
    created = _create(db)

    with pytest.raises(NoChanges):
        schools.update_school(db, created.id, changes={}, actor="admin:1")


def test_a_blank_field_names_itself(db):
    created = _create(db)

    with pytest.raises(BlankField) as raised:
        schools.update_school(db, created.id, changes={"city": "  "}, actor="admin:1")

    assert raised.value.field == "city"


def test_an_invalid_payment_status_is_refused(db):
    created = _create(db)

    with pytest.raises(InvalidPaymentStatus):
        schools.update_school(
            db, created.id, changes={"payment_status": "nearly paid"}, actor="admin:1"
        )


def test_an_empty_invoice_url_becomes_null(db):
    """The column is nullable; "" would render as a link to nowhere."""
    created = _create(db, invoiceURL="https://example.test/i.pdf")

    schools.update_school(db, created.id, changes={"invoiceURL": "   "}, actor="admin:1")

    assert db.get(School, created.id).invoiceURL is None


def test_renaming_rewrites_the_delegate_labels(db, factory):
    """The label is the only place the school's name is denormalised."""
    created = _create(db, name="Lincoln High")
    db.commit()
    school = db.get(School, created.id)
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")
    account = db.get(Account, delegate.account_id)
    account.name = "Lincoln High - #1"
    db.commit()

    detail = schools.update_school(
        db, created.id, changes={"school_name": "Lincoln Academy"}, actor="admin:1"
    )

    assert detail.delegates[0].name == "Lincoln Academy - #1"
    assert account.name == "Lincoln Academy - #1"


def test_a_rename_that_would_truncate_a_label_is_refused(db, factory):
    """The label column is 100 characters; refuse rather than let Postgres fail mid-update."""
    long_name = "A" * 60
    created = _create(db, name=long_name)
    db.commit()
    school = db.get(School, created.id)
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")
    db.get(Account, delegate.account_id).name = f"{long_name} - #1"
    db.commit()

    with pytest.raises(DelegateLabelsTooLong):
        schools.update_school(
            db, created.id, changes={"school_name": "B" * 100}, actor="admin:1"
        )

    # Nothing was renamed.
    assert db.get(School, created.id).school_name == long_name


def test_renaming_onto_a_taken_name_is_refused(db, factory):
    advisor = factory.account(role="advisor", name="Rival Advisor")
    factory.school(advisor, name="Rival High")
    created = _create(db, name="Lincoln High")

    with pytest.raises(SchoolExists) as raised:
        schools.update_school(
            db, created.id, changes={"school_name": "Rival High"}, actor="admin:1"
        )

    assert raised.value.school_name == "Rival High"


# ---------------------------------------------------------------------------
# update_school_delegate
# ---------------------------------------------------------------------------


def test_a_delegate_can_be_moved(db, factory, committee, school):
    delegate = factory.new_delegate(committee, school, country="France")
    factory.committee("UNSC")

    entry = schools.update_school_delegate(
        db,
        school.account_id,
        delegate.account_id,
        changes={"country": "Spain", "committee": "UNSC"},
        actor="admin:1",
    )

    assert entry.country == "Spain"
    assert entry.committee == "UNSC"


def test_moving_onto_another_delegations_pair_is_refused(db, factory, committee, school):
    """There is no unique constraint on the pair, so the rule lives in the domain."""
    first = factory.new_delegate(committee, school, country="France")
    factory.new_delegate(committee, school, country="Spain")

    with pytest.raises(DelegatePairTaken) as raised:
        schools.update_school_delegate(
            db,
            school.account_id,
            first.account_id,
            changes={"country": "Spain"},
            actor="admin:1",
        )

    assert (raised.value.country, raised.value.committee) == ("Spain", "DISEC")


def test_moving_to_an_unknown_committee_is_refused(db, factory, committee, school):
    delegate = factory.new_delegate(committee, school, country="France")

    with pytest.raises(UnknownCommittee):
        schools.update_school_delegate(
            db,
            school.account_id,
            delegate.account_id,
            changes={"committee": "NONEXISTENT"},
            actor="admin:1",
        )


def test_a_delegate_of_another_school_is_refused(db, factory, committee, school):
    rival = factory.account(role="advisor", name="Rival Advisor")
    rival_school = factory.school(rival, name="Rival High")
    foreign = factory.new_delegate(committee, rival_school, country="Spain")

    with pytest.raises(DelegateNotInSchool):
        schools.update_school_delegate(
            db, school.account_id, foreign.account_id, changes={"country": "Italy"}, actor="admin:1"
        )


def test_a_blank_field_and_an_empty_change_set_are_refused(db, factory, committee, school):
    delegate = factory.new_delegate(committee, school, country="France")

    with pytest.raises(NoChanges):
        schools.update_school_delegate(
            db, school.account_id, delegate.account_id, changes={}, actor="admin:1"
        )

    with pytest.raises(BlankField) as raised:
        schools.update_school_delegate(
            db,
            school.account_id,
            delegate.account_id,
            changes={"country": "  "},
            actor="admin:1",
        )

    assert raised.value.field == "country"


# ---------------------------------------------------------------------------
# delete_school
# ---------------------------------------------------------------------------


def test_a_mismatched_confirmation_is_refused(db):
    created = _create(db)

    with pytest.raises(ConfirmationMismatch):
        schools.delete_school(db, created.id, confirm="Wrong Name", actor="admin:1")


def test_deleting_removes_the_school_its_advisor_its_delegates_and_its_files(
    db, factory, papers_dir
):
    created = _create(db)
    db.commit()
    school = db.get(School, created.id)
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")
    factory.upload(delegate, file_path="paper.pdf", write_bytes=b"%PDF-paper")
    account_id = delegate.account_id

    result = schools.delete_school(db, created.id, confirm="Lincoln High", actor="admin:1")

    assert (result.school, result.delegates_deleted, result.files_deleted) == (
        "Lincoln High",
        1,
        1,
    )
    # The `schools` row is removed by the database's cascade, which the session's identity
    # map never hears about, so a SELECT is the honest probe here.
    assert db.scalars(select(School).where(School.account_id == created.id)).first() is None
    assert db.scalars(select(Account).where(Account.id == created.id)).first() is None
    assert db.scalars(select(Delegates).where(Delegates.account_id == account_id)).first() is None
    assert not (papers_dir / "paper.pdf").exists()


def test_deleting_one_school_leaves_the_others(db, factory, committee):
    advisor = factory.account(role="advisor", name="Rival Advisor")
    rival_school = factory.school(advisor, name="Rival High")
    survivor = factory.new_delegate(committee, rival_school, country="Spain")
    created = _create(db, name="Lincoln High")

    schools.delete_school(db, created.id, confirm="Lincoln High", actor="admin:1")

    assert db.get(Delegates, survivor.account_id) is not None


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_the_detail_reports_has_paper_from_the_bytes(db, factory, papers_dir):
    created = _create(db)
    db.commit()
    school = db.get(School, created.id)
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    assert schools.get_school_detail(db, created.id).delegates[0].has_paper is True

    (papers_dir / "live.pdf").unlink()

    assert schools.get_school_detail(db, created.id).delegates[0].has_paper is False


def test_the_detail_carries_the_advisor_hash_and_the_delegate_hash(db, factory):
    created = _create(db)
    db.commit()
    school = db.get(School, created.id)
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    detail = schools.get_school_detail(db, created.id)

    assert detail.advisor_hash == db.get(Account, created.id).identifier
    assert detail.delegates[0].hash == db.get(Account, delegate.account_id).identifier
