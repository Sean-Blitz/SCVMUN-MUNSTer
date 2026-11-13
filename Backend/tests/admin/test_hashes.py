"""API tests for the admin hash routes (§8.4): mint, reissue, and list login codes.

A hash is the only way into the platform, so these four routes are the credential supply. The
rules that matter:

* one account per *delegation*, so double-delegation partners share a hash - a pair that
  already has one is refused with 409 and "regenerate" is the intended path;
* reissuing replaces ``Account.identifier`` **and** revokes live sessions, so the old code
  cannot log in and an already-open tab stops working;
* ``GET /admin/hashes`` is admin-only and deliberately unmasked - the same exposure the
  advisor route avoids, which is why the advisor route masks.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_hashes.py -v
"""

import pytest
from sqlalchemy import select

import core.audit
from crud.database_schema import Account, AuthSession, Chairs, Delegates

# The four routes, with a body where one is required, for the gate tests.
HASH_ROUTES = [
    (
        "post",
        "/api/admin/hashes",
        {"json": {"school_name": "X", "finalAssignments": {"1": ["DISEC", "France"]}}},
    ),
    (
        "post",
        "/api/admin/hashes/regenerate/delegate",
        {"json": {"committee": "DISEC", "country": "France"}},
    ),
    ("post", "/api/admin/hashes/regenerate/chair", {"json": {"account_id": 1}}),
    ("get", "/api/admin/hashes", {}),
]


def _school(factory, name="Lincoln High"):
    """A school row, which needs its own advisor account as the primary key."""
    advisor = factory.account(role="advisor", name=f"Advisor {name}")
    return factory.school(advisor, name=name)


def _mint(client, headers, school_name, assignments):
    return client.post(
        "/api/admin/hashes",
        json={"school_name": school_name, "finalAssignments": assignments},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", HASH_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", HASH_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    """Minting an access code is the most powerful write in the API; a delegate cannot."""
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# POST /admin/hashes - mint
# ---------------------------------------------------------------------------


def test_minting_creates_one_hash_per_delegate(
    client, db, factory, admin_headers, committee
):
    """Each submitted row becomes an unclaimed delegate account plus its profile row."""
    school = _school(factory)

    response = _mint(
        client,
        admin_headers,
        "Lincoln High",
        {"1": ["DISEC", "France"], "2": ["DISEC", "Spain"]},
    )

    assert response.status_code == 201
    entries = response.json()["hashes"]
    assert [entry["name"] for entry in entries] == [
        "Lincoln High - #1",
        "Lincoln High - #2",
    ]
    # `secrets.token_hex(8)`: the same shape everywhere, so codes look alike in the UI.
    assert all(len(entry["hash"]) == 16 for entry in entries)
    assert len({entry["hash"] for entry in entries}) == 2

    delegates = db.scalars(select(Delegates).order_by(Delegates.country)).all()
    assert [(row.country, row.committee) for row in delegates] == [
        ("France", "DISEC"),
        ("Spain", "DISEC"),
    ]
    assert all(row.school_id == school.account_id for row in delegates)
    # Unclaimed: the delegate claims it through First-Time Register.
    assert all(db.get(Account, row.account_id).password_hash is None for row in delegates)


def test_partners_share_one_hash_and_one_account(client, db, factory, admin_headers, committee):
    """Double delegation partners are one delegation, so they get one login."""
    _school(factory)

    response = _mint(
        client,
        admin_headers,
        "Lincoln High",
        {"1": ["DISEC", "France"], "2": ["DISEC", "France"]},
    )

    entries = response.json()["hashes"]
    assert len(entries) == 2
    assert entries[0]["hash"] == entries[1]["hash"]
    assert len(db.scalars(select(Account).where(Account.role == "delegate")).all()) == 1


def test_the_legacy_three_item_shape_is_accepted(client, db, factory, admin_headers, committee):
    """Old CLI callers sent [committee, committeeType, country]; the middle item is ignored.

    A committee's type belongs to the committee row, so there is no delegate column for it.
    """
    _school(factory)

    response = _mint(
        client,
        admin_headers,
        "Lincoln High",
        {"1": ["DISEC", "General Assembly", "France"]},
    )

    assert response.status_code == 201
    row = db.scalars(select(Delegates)).one()
    assert (row.committee, row.country) == ("DISEC", "France")


def test_the_minted_hashes_are_not_the_advisors(client, factory, admin_headers, committee):
    """The advisor's code is issued by POST /admin/schools and must stay distinct."""
    school = _school(factory)
    advisor_hash = factory.db.get(Account, school.account_id).identifier

    response = _mint(client, admin_headers, "Lincoln High", {"1": ["DISEC", "France"]})

    assert response.json()["hashes"][0]["hash"] != advisor_hash


def test_minting_is_audited_with_the_school_and_count(
    client, factory, admin_headers, committee
):
    _school(factory)
    before = core.audit.read("technical")

    _mint(
        client,
        admin_headers,
        "Lincoln High",
        {"1": ["DISEC", "France"], "2": ["DISEC", "Spain"]},
    )

    written = core.audit.read("technical")[len(before):]
    assert "hash.minted" in written
    assert 'school="Lincoln High"' in written
    assert "count=2" in written


def test_an_unknown_school_is_404_and_says_where_to_create_it(client, admin_headers):
    """Minting does not create the school; the message points at the endpoint that does."""
    response = _mint(client, admin_headers, "Nowhere High", {"1": ["DISEC", "France"]})

    assert response.status_code == 404
    assert response.json() == {
        "message": "Unknown school 'Nowhere High'. Create it with POST /admin/schools first."
    }


def test_an_unknown_committee_is_404(client, factory, admin_headers):
    """A typo must not create a phantom committee; the list is authoritative."""
    _school(factory)

    response = _mint(client, admin_headers, "Lincoln High", {"1": ["NONEXISTENT", "France"]})

    assert response.status_code == 404
    assert response.json() == {
        "message": "Unknown committee 'NONEXISTENT'. Create it on the Committees tab first."
    }


def test_no_assignments_is_400(client, factory, admin_headers):
    _school(factory)

    response = _mint(client, admin_headers, "Lincoln High", {})

    assert response.status_code == 400
    assert response.json() == {"message": "Add at least one delegate."}


@pytest.mark.parametrize("assignment", [["DISEC"], ["DISEC", "GA", "France", "extra"]])
def test_a_row_with_the_wrong_number_of_items_is_400(
    client, factory, admin_headers, assignment
):
    """The message names the offending key, so the admin knows which row to fix."""
    _school(factory)

    response = _mint(client, admin_headers, "Lincoln High", {"1": assignment})

    assert response.status_code == 400
    assert response.json() == {"message": 'Delegate "1" must be [committee, country].'}


@pytest.mark.parametrize("assignment", [["", "France"], ["DISEC", "   "]])
def test_a_blank_committee_or_country_is_400(client, factory, admin_headers, assignment):
    _school(factory)

    response = _mint(client, admin_headers, "Lincoln High", {"1": assignment})

    assert response.status_code == 400
    assert response.json() == {
        "message": 'Delegate "1" needs both a committee and a country.'
    }


def test_a_delegation_that_already_has_a_hash_is_409(
    client, factory, admin_headers, committee, school
):
    """One account per delegation; reissuing is a different operation, and the message says so."""
    factory.new_delegate(committee, school, country="France")
    _school(factory)

    response = _mint(client, admin_headers, "Lincoln High", {"1": ["DISEC", "France"]})

    assert response.status_code == 409
    assert response.json() == {
        "message": "France (DISEC) already has a hash. Use regenerate to issue a new one."
    }


# ---------------------------------------------------------------------------
# POST /admin/hashes/regenerate/delegate
# ---------------------------------------------------------------------------


def test_regenerating_replaces_the_hash(client, db, factory, admin_headers, committee, school):
    delegate = factory.new_delegate(committee, school, country="France")
    account = db.get(Account, delegate.account_id)
    old_hash = account.identifier

    response = client.post(
        "/api/admin/hashes/regenerate/delegate",
        json={"committee": "DISEC", "country": "France"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "France (DISEC)"
    assert body["hash"] != old_hash

    db.expire_all()
    assert account.identifier == body["hash"]
    # The old code is gone, not merely superseded.
    assert db.scalars(select(Account).where(Account.identifier == old_hash)).first() is None


def test_regenerating_revokes_the_live_sessions(
    client, db, factory, admin_headers, committee, school
):
    """A reissued hash must also kill the tab that is already signed in."""
    delegate = factory.new_delegate(committee, school, country="France")
    old_headers = factory.headers(db.get(Account, delegate.account_id))
    theirs = select(AuthSession).where(AuthSession.account_id == delegate.account_id)
    assert db.scalars(theirs).all() != []

    client.post(
        "/api/admin/hashes/regenerate/delegate",
        json={"committee": "DISEC", "country": "France"},
        headers=admin_headers,
    )

    # Only this account's sessions are revoked; the admin's own token is untouched.
    assert db.scalars(theirs).all() == []
    assert client.get("/api/delegate/my-assignment", headers=old_headers).status_code == 401


def test_regenerating_an_unknown_delegation_is_404(client, factory, admin_headers, committee):
    response = client.post(
        "/api/admin/hashes/regenerate/delegate",
        json={"committee": "DISEC", "country": "Spain"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No delegate found for Spain (DISEC)."}


# ---------------------------------------------------------------------------
# POST /admin/hashes/regenerate/chair
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


def test_regenerating_a_chair_hash_uses_the_account_id(
    client, db, factory, admin_headers, committee
):
    """Chairs have no committee+country pair, so the id is the key."""
    chair_account = _chair(factory, committee)
    old_hash = chair_account.identifier

    response = client.post(
        "/api/admin/hashes/regenerate/chair",
        json={"account_id": chair_account.id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Chair Person"
    assert body["hash"] != old_hash

    db.expire_all()
    assert chair_account.identifier == body["hash"]


def test_regenerating_a_chair_hash_revokes_their_sessions(
    client, db, factory, admin_headers, committee
):
    chair_account = _chair(factory, committee)
    factory.headers(chair_account)
    theirs = select(AuthSession).where(AuthSession.account_id == chair_account.id)

    client.post(
        "/api/admin/hashes/regenerate/chair",
        json={"account_id": chair_account.id},
        headers=admin_headers,
    )

    assert db.scalars(theirs).all() == []


def test_a_chair_account_that_does_not_exist_is_404(client, factory, admin_headers):
    response = client.post(
        "/api/admin/hashes/regenerate/chair",
        json={"account_id": 999_999},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No chair has that account id."}


def test_an_account_without_a_chair_profile_is_404(client, factory, admin_headers):
    """An account id alone is not enough: the resource is the chair, not the account."""
    account = factory.account(role="chair", name="Unattached Chair")

    response = client.post(
        "/api/admin/hashes/regenerate/chair",
        json={"account_id": account.id},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No chair has that account id."}


# ---------------------------------------------------------------------------
# GET /admin/hashes
# ---------------------------------------------------------------------------


def test_the_list_returns_every_delegate_hash_in_name_order(
    client, factory, admin_headers, committee, school
):
    """Admin-only, so nothing is masked: these are the real codes.

    The accounts are named out of order on purpose - the list sorts by the label the hash
    tooling displays, not by insertion.
    """
    second = factory.delegate(
        factory.account(role="delegate", name="Rival High - #1"),
        committee=committee,
        school=school,
        country="Spain",
    )
    first = factory.delegate(
        factory.account(role="delegate", name="Lincoln High - #1"),
        committee=committee,
        school=school,
        country="France",
    )

    response = client.get("/api/admin/hashes", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "hashes": [
            {
                "name": "Lincoln High - #1",
                "hash": factory.db.get(Account, first.account_id).identifier,
            },
            {
                "name": "Rival High - #1",
                "hash": factory.db.get(Account, second.account_id).identifier,
            },
        ]
    }


def test_the_list_can_be_narrowed_to_one_school(client, factory, admin_headers, committee):
    lincoln = _school(factory, "Lincoln High")
    rival = _school(factory, "Rival High")
    mine = factory.new_delegate(committee, lincoln, country="France")
    factory.new_delegate(committee, rival, country="Spain")

    response = client.get(
        "/api/admin/hashes", params={"schoolName": "Lincoln High"}, headers=admin_headers
    )

    entries = response.json()["hashes"]
    assert len(entries) == 1
    assert entries[0]["hash"] == factory.db.get(Account, mine.account_id).identifier


def test_an_unknown_school_filter_matches_nothing(client, factory, admin_headers, committee):
    """Not an error: a filter that matches no row is a legitimate empty answer."""
    factory.new_delegate(committee, _school(factory, "Lincoln High"), country="France")

    response = client.get(
        "/api/admin/hashes", params={"schoolName": "No Such School"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"hashes": []}


def test_non_delegate_accounts_are_excluded(client, factory, admin_headers, committee):
    """The list joins through ``delegates``, so advisors, chairs and admins have no code here."""
    factory.new_delegate(committee, _school(factory, "Lincoln High"), country="France")
    _chair(factory, committee)

    response = client.get("/api/admin/hashes", headers=admin_headers)

    assert len(response.json()["hashes"]) == 1
