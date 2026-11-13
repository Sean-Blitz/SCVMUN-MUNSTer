"""API tests for the committee routes (§8.10): the conference's structural records.

A committee's **name is its primary key**, and three tables reference it by value -
``delegates.committee``, ``chairs.committee_name`` and ``broadcasts.committee_name`` - none of
which cascades on update. So renaming is the delicate operation here: the server inserts the
new row, repoints all three, then removes the old one, in a single transaction. A failure
anywhere leaves the old name and its children intact.

The other rules: a duplicate name is a 409, a blank one is a 400, and the two membership routes
are scoped by the committee in the path, so an id from another committee is simply not found.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_committees.py -v
"""

import pytest
from sqlalchemy import select

import core.audit
from crud.database_schema import Account, Broadcast, Chairs, Delegates, School

COMMITTEE_ROUTES = [
    ("get", "/api/admin/committees", {}),
    ("post", "/api/admin/committees", {"json": {"committee_name": "X"}}),
    ("get", "/api/admin/committees/DISEC", {}),
    ("patch", "/api/admin/committees/DISEC", {"json": {"topic": "t"}}),
    ("post", "/api/admin/committees/DISEC/chairs", {"json": {"name": "C", "email": "c@x.test"}}),
    ("patch", "/api/admin/committees/DISEC/chairs/1", {"json": {"name": "C"}}),
    ("delete", "/api/admin/committees/DISEC/chairs/1", {}),
    ("delete", "/api/admin/committees/DISEC/delegates/1", {}),
]


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", COMMITTEE_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", COMMITTEE_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# Create / list / detail
# ---------------------------------------------------------------------------


def test_a_committee_needs_only_a_name(client, admin_headers):
    response = client.post(
        "/api/admin/committees", json={"committee_name": "UNSC"}, headers=admin_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["committee_name"] == "UNSC"
    assert body["committee_type"] is None
    assert body["topic"] is None
    assert body["chairs"] == []
    assert body["delegates"] == []


def test_type_and_topic_are_stored(client, admin_headers):
    response = client.post(
        "/api/admin/committees",
        json={
            "committee_name": "UNSC",
            "committee_type": "General Assembly",
            "topic": "Maritime security",
        },
        headers=admin_headers,
    )

    assert response.json()["committee_type"] == "General Assembly"
    assert response.json()["topic"] == "Maritime security"


def test_a_duplicate_name_is_409(client, admin_headers):
    client.post(
        "/api/admin/committees", json={"committee_name": "UNSC"}, headers=admin_headers
    )

    response = client.post(
        "/api/admin/committees", json={"committee_name": "UNSC"}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json() == {"message": "A committee named 'UNSC' already exists."}


def test_a_blank_name_is_400(client, admin_headers):
    response = client.post(
        "/api/admin/committees", json={"committee_name": "   "}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json() == {"message": "committee_name cannot be blank."}


def test_the_list_is_the_names(client, factory, admin_headers):
    factory.committee("UNSC")
    factory.committee("DISEC")

    names = client.get("/api/admin/committees", headers=admin_headers).json()

    assert set(names) == {"DISEC", "UNSC"}


def test_the_detail_lists_chairs_and_delegates_with_their_hashes(
    client, factory, admin_headers, committee, school
):
    """A committee spans schools, so each delegate carries its school's name."""
    created = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    ).json()
    delegate = factory.new_delegate(committee, school, country="France")

    body = client.get("/api/admin/committees/DISEC", headers=admin_headers).json()

    assert body["chairs"] == [
        {
            "account_id": created["account_id"],
            "name": "Chair Person",
            "email": "chair@example.test",
            "hash": created["hash"],
        }
    ]
    (entry,) = body["delegates"]
    assert entry["account_id"] == delegate.account_id
    assert entry["country"] == "France"
    assert entry["school_name"] == "Test High School"
    assert entry["paper_status"] == "unsubmitted"


def test_an_unknown_committee_is_404(client, admin_headers):
    response = client.get("/api/admin/committees/NONEXISTENT", headers=admin_headers)

    assert response.status_code == 404
    assert response.json() == {
        "message": "Unknown committee 'NONEXISTENT'. Create it on the Committees tab first."
    }


# ---------------------------------------------------------------------------
# PATCH /admin/committees/{name}
# ---------------------------------------------------------------------------


def test_type_and_topic_can_be_edited(client, admin_headers, committee):
    response = client.patch(
        "/api/admin/committees/DISEC", json={"topic": "Cyber norms"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["topic"] == "Cyber norms"


def test_an_empty_patch_is_400(client, admin_headers, committee):
    response = client.patch(
        "/api/admin/committees/DISEC", json={}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json() == {"message": "No changes were sent."}


def test_renaming_repoints_everything_that_references_the_name(
    client, factory, db, admin_headers, committee, school
):
    """The name is a foreign key in three tables and none of them cascades on update.

    A rename that missed one would leave a delegate, a chair or a broadcast pointing at a
    committee that no longer exists.
    """
    chair = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    ).json()
    delegate = factory.new_delegate(committee, school, country="France")
    client.post(
        "/api/admin/broadcasts",
        json={"kind": "announcement", "body": "For DISEC", "committee_name": "DISEC"},
        headers=admin_headers,
    )

    response = client.patch(
        "/api/admin/committees/DISEC",
        json={"committee_name": "DISEC II"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["committee_name"] == "DISEC II"

    db.expire_all()
    assert db.get(Delegates, delegate.account_id).committee == "DISEC II"
    assert db.get(Chairs, chair["account_id"]).committee_name == "DISEC II"
    assert db.scalars(select(Broadcast)).one().committee_name == "DISEC II"


def test_renaming_onto_a_taken_name_is_409(client, factory, admin_headers, committee):
    factory.committee("UNSC")

    response = client.patch(
        "/api/admin/committees/DISEC", json={"committee_name": "UNSC"}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json() == {"message": "A committee named 'UNSC' already exists."}


def test_renaming_to_a_blank_name_is_400(client, admin_headers, committee):
    response = client.patch(
        "/api/admin/committees/DISEC", json={"committee_name": "  "}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json() == {"message": "committee_name cannot be blank."}


def test_an_edit_is_audited(client, admin_headers, committee):
    before = core.audit.read("technical")

    client.patch("/api/admin/committees/DISEC", json={"topic": "New"}, headers=admin_headers)

    written = core.audit.read("technical")[len(before):]
    assert "committee.updated" in written or "committee.renamed" in written


# ---------------------------------------------------------------------------
# Chairs
# ---------------------------------------------------------------------------


def test_a_chair_can_be_added_with_a_hash(client, db, admin_headers, committee):
    """Nothing else in the API creates a ``chairs`` row, so this is the only way in."""
    response = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Chair Person"
    assert len(body["hash"]) == 16

    account = db.get(Account, body["account_id"])
    assert account.role == "chair"
    assert account.identifier == body["hash"]
    # Unclaimed: the chair registers with this hash, as an advisor does.
    assert account.password_hash is None


def test_adding_a_chair_to_an_unknown_committee_is_404(client, admin_headers):
    response = client.post(
        "/api/admin/committees/NONEXISTENT/chairs",
        json={"name": "Chair", "email": "c@example.test"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"].startswith("Unknown committee 'NONEXISTENT'")


def test_a_chair_can_be_edited(client, admin_headers, committee):
    created = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    ).json()

    response = client.patch(
        f"/api/admin/committees/DISEC/chairs/{created['account_id']}",
        json={"email": "new@example.test"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == "new@example.test"
    assert response.json()["name"] == "Chair Person"


def test_an_empty_chair_patch_is_400(client, admin_headers, committee):
    created = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    ).json()

    response = client.patch(
        f"/api/admin/committees/DISEC/chairs/{created['account_id']}",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "No changes were sent."}


def test_a_chair_of_another_committee_cannot_be_edited(
    client, factory, admin_headers, committee
):
    """The path's committee must own the chair, so ids cannot be used to reach across."""
    unsc = factory.committee("UNSC")
    created = client.post(
        "/api/admin/committees/UNSC/chairs",
        json={"name": "Other Chair", "email": "other@example.test"},
        headers=admin_headers,
    ).json()
    assert unsc.committee_name == "UNSC"

    response = client.patch(
        f"/api/admin/committees/DISEC/chairs/{created['account_id']}",
        json={"name": "Renamed"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "That chair is not part of this committee."
    }


def test_a_chair_can_be_removed(client, db, admin_headers, committee):
    created = client.post(
        "/api/admin/committees/DISEC/chairs",
        json={"name": "Chair Person", "email": "chair@example.test"},
        headers=admin_headers,
    ).json()

    response = client.delete(
        f"/api/admin/committees/DISEC/chairs/{created['account_id']}", headers=admin_headers
    )

    assert response.status_code == 204
    db.expire_all()
    assert db.get(Chairs, created["account_id"]) is None
    assert db.get(Account, created["account_id"]) is None


# ---------------------------------------------------------------------------
# Removing a delegate from a committee
# ---------------------------------------------------------------------------


def test_removing_a_delegate_deletes_their_rows_and_paper(
    client, factory, db, admin_headers, committee, school, papers_dir
):
    """Their rows, their hash and their stored paper: the same ordering as deleting a school.

    The file is unlinked after the commit because a cascade removes rows, not bytes.
    """
    delegate = factory.new_delegate(committee, school, country="France")
    factory.upload(delegate, file_path="paper.pdf", write_bytes=b"%PDF-paper")
    # Read the id now: once the row is gone, touching any attribute of this instance (even
    # the primary key) makes SQLAlchemy try to refresh it and raise ObjectDeletedError.
    account_id = delegate.account_id

    response = client.delete(
        f"/api/admin/committees/DISEC/delegates/{account_id}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "delegate": "France",
        "school": "Test High School",
        "files_deleted": 1,
    }

    db.expire_all()
    assert db.scalars(
        select(Delegates).where(Delegates.account_id == account_id)
    ).first() is None
    assert db.scalars(select(Account).where(Account.id == account_id)).first() is None
    assert not (papers_dir / "paper.pdf").exists()


def test_a_delegate_of_another_committee_cannot_be_removed(
    client, factory, admin_headers, committee, school
):
    unsc = factory.committee("UNSC")
    foreign = factory.new_delegate(unsc, school, country="Italy")

    response = client.delete(
        f"/api/admin/committees/DISEC/delegates/{foreign.account_id}", headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "That delegate is not in this committee."
    }


def test_the_school_row_survives_removing_one_delegate(
    client, factory, db, admin_headers, committee, school
):
    """Removing a delegate is not removing a school; the advisor's row is untouched."""
    delegate = factory.new_delegate(committee, school, country="France")

    client.delete(
        f"/api/admin/committees/DISEC/delegates/{delegate.account_id}", headers=admin_headers
    )

    db.expire_all()
    assert db.get(School, school.account_id) is not None
