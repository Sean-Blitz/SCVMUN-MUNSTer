"""API tests for the admin school routes (§8.7, §8.9): create, list, detail, edit, delete.

A school is the anchor row of the whole conference: delegates hang off it, its primary key *is*
the advisor's account id, and its name is baked into every delegate's label ("Lincoln High -
#1"). Two consequences drive most of what is pinned here:

* creating a school creates its advisor account, with no password - the hash returned by the
  POST is the only moment the admin is guaranteed to see it;
* renaming a school rewrites the delegate labels that still carry the old prefix, or the hash
  lists would keep naming a school that no longer exists.

Deleting is the last one: it has to remove delegates before the advisor (``delegates.school_id``
is NO ACTION), and unlink the stored papers because a cascade only removes rows.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_schools.py -v
"""

import pytest
from sqlalchemy import select

import core.audit
from crud.database_schema import Account, Delegates, School

# The six routes, with a body/query where required, for the gate tests.
SCHOOL_ROUTES = [
    ("post", "/api/admin/schools", {"json": {}}),
    ("get", "/api/admin/schools", {}),
    ("get", "/api/admin/schools/1", {}),
    ("patch", "/api/admin/schools/1", {"json": {}}),
    ("patch", "/api/admin/schools/1/delegates/1", {"json": {}}),
    ("delete", "/api/admin/schools/1", {"params": {"confirm": "x"}}),
]


def _body(name="Lincoln High", **overrides):
    """A complete POST /admin/schools body, with fields overridable per test."""
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


def _create(client, headers, name="Lincoln High", **overrides):
    return client.post("/api/admin/schools", json=_body(name, **overrides), headers=headers)


def _mint(client, headers, school_name, assignments):
    return client.post(
        "/api/admin/hashes",
        json={"school_name": school_name, "finalAssignments": assignments},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", SCHOOL_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", SCHOOL_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    """An advisor has a school; only an admin may create or delete one."""
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# POST /admin/schools
# ---------------------------------------------------------------------------


def test_creating_a_school_creates_its_advisor(client, db, admin_headers):
    """A school cannot exist without an advisor: ``schools.account_id`` is that account."""
    response = _create(client, admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Lincoln High"
    assert len(body["advisor_hash"]) == 16

    advisor = db.get(Account, body["id"])
    assert advisor.role == "advisor"
    assert advisor.name == "Advisor Person"
    assert advisor.identifier == body["advisor_hash"]
    # Unclaimed: the advisor registers with this hash, exactly as a delegate does.
    assert advisor.password_hash is None

    school = db.get(School, body["id"])
    assert school.school_name == "Lincoln High"
    assert school.school_address == "1 Test Way"
    assert school.zip_code == "90000"
    assert school.payment_status == "unpaid"
    assert school.invoiceURL is None


def test_payment_status_and_invoice_are_stored(client, db, admin_headers):
    body = _create(
        client,
        admin_headers,
        payment_status="partially paid",
        invoiceURL="https://example.test/invoice.pdf",
    ).json()

    school = db.get(School, body["id"])
    assert school.payment_status == "partially paid"
    assert school.invoiceURL == "https://example.test/invoice.pdf"


def test_a_duplicate_name_is_409(client, admin_headers):
    """The name ties a school's papers, ticks and invoice together, so it is a mistake to surface.
    """
    _create(client, admin_headers, "Lincoln High")

    response = _create(client, admin_headers, "Lincoln High")

    assert response.status_code == 409
    assert response.json() == {"message": "A school named 'Lincoln High' already exists."}


def test_a_blank_required_field_is_400_and_names_the_fields(client, admin_headers):
    """The model accepts whitespace; the domain does not, because the column would be blank."""
    response = _create(client, admin_headers, advisor_phone="   ")

    assert response.status_code == 400
    assert response.json() == {
        "message": "Missing required school details: advisor_phone."
    }


@pytest.mark.parametrize("field", ["city", "state", "head_delegate_email"])
def test_every_required_field_is_checked(client, admin_headers, field):
    response = _create(client, admin_headers, **{field: ""})

    assert response.status_code == 400
    assert response.json()["message"].startswith("Missing required school details:")
    assert field in response.json()["message"]


def test_an_omitted_required_field_is_a_422_from_the_model(client, admin_headers):
    """The model is the first gate; its message still has to read like a sentence."""
    body = _body()
    del body["advisor_phone"]

    response = client.post("/api/admin/schools", json=body, headers=admin_headers)

    assert response.status_code == 422
    assert response.json() == {"message": "Advisor phone is required."}


def test_an_invalid_payment_status_is_400_with_the_options(client, admin_headers):
    response = _create(client, admin_headers, payment_status="half paid")

    assert response.status_code == 400
    assert response.json() == {
        "message": "payment_status must be one of: paid, partially paid, unpaid."
    }


def test_creating_a_school_is_audited(client, admin_headers):
    before = core.audit.read("technical")

    _create(client, admin_headers, "Audited High")

    written = core.audit.read("technical")[len(before):]
    assert "school.created" in written
    assert 'school="Audited High"' in written


# ---------------------------------------------------------------------------
# GET /admin/schools
# ---------------------------------------------------------------------------


def test_the_list_is_ordered_and_carries_the_advisor_hash(client, factory, admin_headers):
    """The hash is included so a mislaid code can be read back without a SQL prompt."""
    rival = factory.account(role="advisor", name="Rival Advisor")
    factory.school(rival, name="Rival High")
    _create(client, admin_headers, "Lincoln High")

    response = client.get("/api/admin/schools", headers=admin_headers)

    assert response.status_code == 200
    schools = response.json()["schools"]
    assert [entry["name"] for entry in schools] == ["Lincoln High", "Rival High"]
    assert all(entry["advisor_hash"] for entry in schools)


def test_the_list_is_empty_before_any_school_exists(client, admin_headers):
    assert client.get("/api/admin/schools", headers=admin_headers).json() == {"schools": []}


# ---------------------------------------------------------------------------
# GET /admin/schools/{id}
# ---------------------------------------------------------------------------


def test_the_detail_returns_the_school_and_its_delegates(client, factory, admin_headers):
    created = _create(client, admin_headers).json()
    factory.committee("DISEC")  # minting requires the committee to exist first
    _mint(client, admin_headers, "Lincoln High", {"1": ["DISEC", "France"]})

    response = client.get(f"/api/admin/schools/{created['id']}", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["advisor_hash"] == created["advisor_hash"]
    assert body["school"]["school_name"] == "Lincoln High"
    assert body["school"]["payment_status"] == "unpaid"

    (delegate,) = body["delegates"]
    assert delegate["name"] == "Lincoln High - #1"
    assert delegate["country"] == "France"
    assert delegate["committee"] == "DISEC"
    assert delegate["paper_status"] == "unsubmitted"
    assert delegate["has_paper"] is False


def test_has_paper_follows_the_bytes_not_the_row(
    client, factory, admin_headers, papers_dir
):
    """A row whose file went missing is exactly what an admin rebuilding a school must see."""
    created = _create(client, admin_headers).json()
    school = factory.db.get(School, created["id"])
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    assert client.get(
        f"/api/admin/schools/{created['id']}", headers=admin_headers
    ).json()["delegates"][0]["has_paper"] is True

    (papers_dir / "live.pdf").unlink()

    assert client.get(
        f"/api/admin/schools/{created['id']}", headers=admin_headers
    ).json()["delegates"][0]["has_paper"] is False


def test_the_detail_lists_delegates_by_committee_then_country(
    client, factory, admin_headers
):
    created = _create(client, admin_headers).json()
    school = factory.db.get(School, created["id"])
    unsc = factory.committee("UNSC")
    disec = factory.committee("DISEC")
    factory.new_delegate(unsc, school, country="France")
    factory.new_delegate(disec, school, country="Spain")
    factory.new_delegate(disec, school, country="Argentina")

    delegates = client.get(
        f"/api/admin/schools/{created['id']}", headers=admin_headers
    ).json()["delegates"]

    assert [(entry["committee"], entry["country"]) for entry in delegates] == [
        ("DISEC", "Argentina"),
        ("DISEC", "Spain"),
        ("UNSC", "France"),
    ]


def test_an_unknown_school_id_is_404(client, admin_headers):
    response = client.get("/api/admin/schools/999999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json() == {"message": "No school with id 999999."}


# ---------------------------------------------------------------------------
# PATCH /admin/schools/{id}
# ---------------------------------------------------------------------------


def test_a_patch_only_changes_the_fields_it_sends(client, db, admin_headers):
    created = _create(client, admin_headers).json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"city": "Newville"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    school = db.get(School, created["id"])
    assert school.city == "Newville"
    assert school.state == "CA"  # untouched
    assert school.advisor_email == "advisor@example.test"


def test_renaming_rewrites_the_delegate_labels(client, factory, db, admin_headers):
    """The label lives in ``accounts.name`` as "<school> - #<key>", so a rename has to move it.

    Without this the hash lists keep showing a school that no longer exists.
    """
    created = _create(client, admin_headers, "Lincoln High").json()
    factory.committee("DISEC")
    _mint(client, admin_headers, "Lincoln High", {"1": ["DISEC", "France"]})

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"school_name": "Lincoln Academy"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["delegates"][0]["name"] == "Lincoln Academy - #1"
    assert db.get(School, created["id"]).school_name == "Lincoln Academy"


def test_renaming_onto_a_taken_name_is_409(client, factory, admin_headers):
    rival = factory.account(role="advisor", name="Rival Advisor")
    factory.school(rival, name="Rival High")
    created = _create(client, admin_headers, "Lincoln High").json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"school_name": "Rival High"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json() == {"message": "A school named 'Rival High' already exists."}


def test_a_blank_field_is_400(client, admin_headers):
    created = _create(client, admin_headers).json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"city": "   "},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "city cannot be blank."}


def test_an_invalid_payment_status_is_400(client, admin_headers):
    created = _create(client, admin_headers).json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"payment_status": "nearly paid"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["message"].startswith("payment_status must be one of:")


def test_an_empty_patch_is_400(client, admin_headers):
    """A no-op save is a mistake in the view, not a silent success."""
    created = _create(client, admin_headers).json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}", json={}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json() == {"message": "No changes were sent."}


def test_null_clears_the_invoice_url(client, db, admin_headers):
    """Sending ``null`` for invoiceURL is how the view removes an invoice."""
    created = _create(client, admin_headers, invoiceURL="https://example.test/i.pdf").json()

    response = client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"invoiceURL": None},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert db.get(School, created["id"]).invoiceURL is None


def test_patching_an_unknown_school_is_404(client, admin_headers):
    response = client.patch(
        "/api/admin/schools/999999", json={"city": "Newville"}, headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No school with id 999999."}


def test_an_update_is_audited_with_the_changed_fields(client, admin_headers):
    created = _create(client, admin_headers).json()
    before = core.audit.read("technical")

    client.patch(
        f"/api/admin/schools/{created['id']}",
        json={"city": "Newville", "state": "NY"},
        headers=admin_headers,
    )

    written = core.audit.read("technical")[len(before):]
    assert "school.updated" in written
    assert "fields=city,state" in written


# ---------------------------------------------------------------------------
# PATCH /admin/schools/{id}/delegates/{account_id}
# ---------------------------------------------------------------------------


def _delegate_of(client, db, headers, school_id):
    detail = client.get(f"/api/admin/schools/{school_id}", headers=headers).json()
    return detail["delegates"][0], db


def test_a_delegate_can_be_moved_to_another_country(client, factory, db, admin_headers, school):
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{delegate.account_id}",
        json={"country": "Spain"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["country"] == "Spain"
    db.expire_all()
    assert db.get(Delegates, delegate.account_id).country == "Spain"


def test_a_delegate_can_be_moved_to_another_committee(client, factory, db, admin_headers, school):
    factory.committee("UNSC")
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{delegate.account_id}",
        json={"committee": "UNSC"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["committee"] == "UNSC"


def test_moving_a_delegate_to_an_unknown_committee_is_404(
    client, factory, admin_headers, school
):
    """The committee list is authoritative: a typo must not create a phantom.

    This used to answer 500: `_school_error` had no ``UnknownCommittee`` branch, so the
    domain failure hit the catch-all. The message matches the one the hash routes return for
    the same mistake.
    """
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{delegate.account_id}",
        json={"committee": "NONEXISTENT"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "Unknown committee 'NONEXISTENT'. Create it on the Committees tab first."
    }


def test_moving_onto_another_delegations_pair_is_409(
    client, factory, admin_headers, school
):
    """One hash per delegation; the unique pair is enforced here because no constraint does."""
    committee = factory.committee("DISEC")
    first = factory.new_delegate(committee, school, country="France")
    factory.new_delegate(committee, school, country="Spain")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{first.account_id}",
        json={"country": "Spain"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "message": "Spain (DISEC) already has a delegate hash."
    }


def test_a_delegate_of_another_school_cannot_be_edited(
    client, factory, admin_headers, school
):
    """The school id in the path must own the delegate, so ids cannot be used to reach across."""
    rival = factory.account(role="advisor", name="Rival Advisor")
    rival_school = factory.school(rival, name="Rival High")
    foreign = factory.new_delegate(factory.committee("DISEC"), rival_school, country="Spain")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{foreign.account_id}",
        json={"country": "Italy"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "That delegate is not part of this school."
    }


def test_an_empty_delegate_patch_is_400(client, factory, admin_headers, school):
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{delegate.account_id}",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "No changes were sent."}


def test_a_blank_country_is_400(client, factory, admin_headers, school):
    delegate = factory.new_delegate(factory.committee("DISEC"), school, country="France")

    response = client.patch(
        f"/api/admin/schools/{school.account_id}/delegates/{delegate.account_id}",
        json={"country": "  "},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "country cannot be blank."}


# ---------------------------------------------------------------------------
# DELETE /admin/schools/{id}
# ---------------------------------------------------------------------------


def test_deleting_a_school_removes_its_delegates_and_papers(
    client, factory, db, admin_headers, papers_dir
):
    """Order matters: delegates go before the advisor account whose deletion cascades the
    school away. Files are unlinked here because a cascade only removes rows.
    """
    created = _create(client, admin_headers).json()
    factory.committee("DISEC")
    _mint(client, admin_headers, "Lincoln High", {"1": ["DISEC", "France"]})

    delegate = db.scalars(
        select(Delegates).where(Delegates.school_id == created["id"])
    ).one()
    factory.upload(delegate, file_path="paper.pdf", write_bytes=b"%PDF-paper")

    response = client.delete(
        f"/api/admin/schools/{created['id']}",
        params={"confirm": "Lincoln High"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "school": "Lincoln High",
        "delegates_deleted": 1,
        "files_deleted": 1,
    }

    db.expire_all()
    assert db.get(School, created["id"]) is None
    assert db.get(Account, created["id"]) is None
    assert db.scalars(select(Delegates)).all() == []
    assert not (papers_dir / "paper.pdf").exists()


def test_a_mismatched_confirmation_is_400(client, admin_headers):
    """The dialog lives in the browser, so the server checks intent itself."""
    created = _create(client, admin_headers).json()

    response = client.delete(
        f"/api/admin/schools/{created['id']}",
        params={"confirm": "Wrong Name"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "To delete a school, `confirm` must repeat its current name exactly."
    }


def test_the_confirmation_is_required(client, admin_headers):
    created = _create(client, admin_headers).json()

    response = client.delete(f"/api/admin/schools/{created['id']}", headers=admin_headers)

    assert response.status_code == 422
    assert response.json() == {"message": "Confirm is required."}


def test_deleting_an_unknown_school_is_404(client, admin_headers):
    response = client.delete(
        "/api/admin/schools/999999", params={"confirm": "x"}, headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No school with id 999999."}


def test_deleting_one_school_leaves_the_others(client, factory, db, admin_headers, school):
    """The blast radius is one school; a rival's delegates must survive untouched."""
    created = _create(client, admin_headers).json()
    survivor = factory.new_delegate(factory.committee("DISEC"), school, country="Spain")

    client.delete(
        f"/api/admin/schools/{created['id']}",
        params={"confirm": "Lincoln High"},
        headers=admin_headers,
    )

    db.expire_all()
    assert db.get(Delegates, survivor.account_id) is not None
    assert db.get(School, school.account_id) is not None


def test_a_deletion_is_audited(client, admin_headers):
    created = _create(client, admin_headers).json()
    before = core.audit.read("technical")

    client.delete(
        f"/api/admin/schools/{created['id']}",
        params={"confirm": "Lincoln High"},
        headers=admin_headers,
    )

    written = core.audit.read("technical")[len(before):]
    assert "school.deleted" in written
    assert 'school="Lincoln High"' in written
