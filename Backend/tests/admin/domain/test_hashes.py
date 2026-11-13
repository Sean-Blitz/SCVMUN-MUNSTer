"""Domain tests for ``core.domain.admin.hashes`` (§8.4).

The hash routes are the credential supply, and the domain is where the real rules live:

* one account per *delegation*, so double-delegation partners share a hash, and a pair that
  already has one is refused - "regenerate" is the intended path, not "mint again";
* reissuing replaces ``Account.identifier`` **and** revokes live sessions, so the old code
  cannot log in and an already-open tab stops working;
* a reissued chair hash is keyed by account id, because a chair has no committee+country pair.

The exceptions carry the data the endpoints put into their messages (the offending key, the
school name, the committee name), which is why those attributes are asserted rather than the
``str()``.
"""

import pytest
from sqlalchemy import select

import core.audit
from core.domain.admin import hashes
from core.domain.errors import (
    BadAssignmentShape,
    BadAssignmentValue,
    ChairNotFound,
    DelegateAssignmentNotFound,
    DelegationAlreadyHasHash,
    NoAssignments,
    UnknownCommittee,
    UnknownSchool,
)
from crud.database_schema import Account, AuthSession, Chairs, Delegates


def _school(factory, name="Lincoln High"):
    advisor = factory.account(role="advisor", name=f"Advisor {name}")
    return factory.school(advisor, name=name)


def _mint(db, **kwargs):
    return hashes.mint_delegate_hashes(db, actor="admin:1", **kwargs)


# ---------------------------------------------------------------------------
# mint_delegate_hashes
# ---------------------------------------------------------------------------


def test_minting_creates_one_unclaimed_account_per_delegation(db, factory, committee):
    school = _school(factory)

    result = _mint(
        db,
        school_name="Lincoln High",
        assignments={"1": ["DISEC", "France"], "2": ["DISEC", "Spain"]},
    )

    assert [entry.name for entry in result.hashes] == [
        "Lincoln High - #1",
        "Lincoln High - #2",
    ]
    assert all(len(entry.hash) == 16 for entry in result.hashes)

    rows = db.scalars(select(Delegates).order_by(Delegates.country)).all()
    assert [(row.committee, row.country) for row in rows] == [
        ("DISEC", "France"),
        ("DISEC", "Spain"),
    ]
    assert all(row.school_id == school.account_id for row in rows)
    assert all(db.get(Account, row.account_id).password_hash is None for row in rows)


def test_partners_share_one_account_and_one_hash(db, factory, committee):
    """Two rows, one delegation: the database never tracks which partner is which."""
    _school(factory)

    result = _mint(
        db,
        school_name="Lincoln High",
        assignments={"1": ["DISEC", "France"], "2": ["DISEC", "France"]},
    )

    assert result.hashes[0].hash == result.hashes[1].hash
    assert len(db.scalars(select(Account).where(Account.role == "delegate")).all()) == 1


def test_the_legacy_three_item_shape_drops_the_committee_type(db, factory, committee):
    """A committee's type belongs to the committee row, not the delegate, so it is ignored."""
    _school(factory)

    _mint(db, school_name="Lincoln High", assignments={"1": ["DISEC", "GA", "France"]})

    assert db.scalars(select(Delegates)).one().country == "France"


def test_no_assignments_is_refused(db, factory):
    _school(factory)

    with pytest.raises(NoAssignments):
        _mint(db, school_name="Lincoln High", assignments={})


@pytest.mark.parametrize("assignment", [["DISEC"], ["DISEC", "GA", "France", "extra"]])
def test_a_row_of_the_wrong_arity_names_its_key(db, factory, committee, assignment):
    _school(factory)

    with pytest.raises(BadAssignmentShape) as raised:
        _mint(db, school_name="Lincoln High", assignments={"1": assignment})

    assert raised.value.key == "1"


@pytest.mark.parametrize("assignment", [["", "France"], ["DISEC", "  "]])
def test_a_blank_value_names_its_key(db, factory, committee, assignment):
    _school(factory)

    with pytest.raises(BadAssignmentValue) as raised:
        _mint(db, school_name="Lincoln High", assignments={"1": assignment})

    assert raised.value.key == "1"


def test_an_unknown_school_is_refused(db, committee):
    with pytest.raises(UnknownSchool) as raised:
        _mint(db, school_name="Nowhere High", assignments={"1": ["DISEC", "France"]})

    assert raised.value.school_name == "Nowhere High"


def test_an_unknown_committee_is_refused(db, factory):
    _school(factory)

    with pytest.raises(UnknownCommittee) as raised:
        _mint(db, school_name="Lincoln High", assignments={"1": ["NONEXISTENT", "France"]})

    assert raised.value.committee_name == "NONEXISTENT"


def test_a_delegation_that_already_has_a_hash_is_refused(
    db, factory, committee, school
):
    factory.new_delegate(committee, school, country="France")
    _school(factory)

    with pytest.raises(DelegationAlreadyHasHash) as raised:
        _mint(db, school_name="Lincoln High", assignments={"1": ["DISEC", "France"]})

    assert (raised.value.country, raised.value.committee) == ("France", "DISEC")


def test_minting_is_audited(db, factory, committee):
    _school(factory)
    before = core.audit.read("technical")

    _mint(
        db,
        school_name="Lincoln High",
        assignments={"1": ["DISEC", "France"], "2": ["DISEC", "Spain"]},
    )

    written = core.audit.read("technical")[len(before):]
    assert "hash.minted" in written
    assert 'school="Lincoln High"' in written
    assert "count=2" in written


# ---------------------------------------------------------------------------
# revoke_sessions
# ---------------------------------------------------------------------------


def test_revocation_is_scoped_to_the_one_account(db, factory):
    """Reissuing one delegate's hash must not sign out anybody else."""
    account = factory.account(role="delegate")
    other = factory.account(role="delegate")
    factory.headers(account)
    factory.headers(other)
    keep = select(AuthSession).where(AuthSession.account_id == other.id)

    hashes.revoke_sessions(db, account.id)

    assert db.scalars(keep).all() != []
    assert db.scalars(
        select(AuthSession).where(AuthSession.account_id == account.id)
    ).all() == []


# ---------------------------------------------------------------------------
# reissue_delegate_hash
# ---------------------------------------------------------------------------


def test_reissuing_a_delegate_hash_replaces_it_and_ends_the_sessions(
    db, factory, committee, school
):
    delegate = factory.new_delegate(committee, school, country="France")
    account = db.get(Account, delegate.account_id)
    old_hash = account.identifier
    factory.headers(account)

    entry = hashes.reissue_delegate_hash(
        db, committee="DISEC", country="France", actor="admin:1"
    )

    assert entry.name == "France (DISEC)"
    assert entry.hash != old_hash
    assert db.scalars(select(AuthSession)).all() == []
    assert db.scalars(select(Account).where(Account.identifier == old_hash)).first() is None


def test_reissuing_an_unknown_delegation_carries_the_pair(db):
    with pytest.raises(DelegateAssignmentNotFound) as raised:
        hashes.reissue_delegate_hash(
            db, committee="DISEC", country="Spain", actor="admin:1"
        )

    assert (raised.value.country, raised.value.committee) == ("Spain", "DISEC")


# ---------------------------------------------------------------------------
# reissue_chair_hash
# ---------------------------------------------------------------------------


def _chair(factory, committee, *, name="Chair Person"):
    account = factory.account(role="chair", name=name)
    factory.db.add(
        Chairs(
            account_id=account.id,
            name=name,
            committee_name=committee.committee_name,
            email="chair@example.test",
        )
    )
    factory.db.commit()
    return account


def test_reissuing_a_chair_hash_is_keyed_by_account_id(db, factory, committee):
    account = _chair(factory, committee)
    old_hash = account.identifier

    entry = hashes.reissue_chair_hash(db, account_id=account.id, actor="admin:1")

    assert entry.name == "Chair Person"
    assert entry.hash != old_hash
    assert db.get(Account, account.id).identifier == entry.hash


def test_a_chair_reissue_revokes_their_sessions(db, factory, committee):
    account = _chair(factory, committee)
    factory.headers(account)

    hashes.reissue_chair_hash(db, account_id=account.id, actor="admin:1")

    assert db.scalars(select(AuthSession)).all() == []


def test_an_account_without_a_chair_profile_is_refused(db, factory):
    """The resource is the chair, not the account, so an unattached id is not a chair."""
    account = factory.account(role="chair")

    with pytest.raises(ChairNotFound):
        hashes.reissue_chair_hash(db, account_id=account.id, actor="admin:1")


# ---------------------------------------------------------------------------
# list_hashes
# ---------------------------------------------------------------------------


def test_the_list_returns_real_hashes_in_name_order(db, factory, committee, school):
    first = factory.delegate(
        factory.account(role="delegate", name="Lincoln High - #1"),
        committee=committee,
        school=school,
        country="France",
    )
    second = factory.delegate(
        factory.account(role="delegate", name="Rival High - #1"),
        committee=committee,
        school=school,
        country="Spain",
    )

    result = hashes.list_hashes(db)

    assert [(entry.name, entry.hash) for entry in result.hashes] == [
        ("Lincoln High - #1", db.get(Account, first.account_id).identifier),
        ("Rival High - #1", db.get(Account, second.account_id).identifier),
    ]


def test_the_list_can_be_narrowed_to_a_school(db, factory, committee):
    lincoln = _school(factory, "Lincoln High")
    rival = _school(factory, "Rival High")
    factory.new_delegate(committee, lincoln, country="France")
    factory.new_delegate(committee, rival, country="Spain")

    assert len(hashes.list_hashes(db).hashes) == 2
    narrowed = hashes.list_hashes(db, school_name="Lincoln High")
    assert [entry.name for entry in narrowed.hashes] == ["Test Person"]


def test_an_unknown_school_filter_matches_nothing(db, factory, committee):
    factory.new_delegate(committee, _school(factory), country="France")

    assert hashes.list_hashes(db, school_name="No Such School").hashes == []


def test_non_delegate_accounts_have_no_hash_in_the_list(db, factory, committee):
    factory.new_delegate(committee, _school(factory), country="France")
    _chair(factory, committee)

    assert len(hashes.list_hashes(db).hashes) == 1
