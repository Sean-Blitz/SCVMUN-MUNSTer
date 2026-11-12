"""API tests for /advisor/*, driven through Starlette's TestClient.

The advisor surface is four routes, and the thing they all have in common is *scoping*: the
school is resolved from the bearer token and never from the request, so one advisor can never
read another school's roster, papers or checklist. Most of what is pinned below is that rule
plus the credential-reveal contract.

Two failure codes are load-bearing and easy to regress:

* a wrong re-authentication password is **403, not 401** - the frontend's axios interceptor
  treats every 401 as a dead session and would log the advisor out instead of showing the
  message inside the password modal;
* a delegate from another school and a delegate that does not exist both answer **404 with
  the same body**, so the endpoint is not an oracle for "this id exists".

Run with::

    cd Backend && .venv/bin/python -m pytest tests/advisors/test_endpoints.py -v
"""

import pytest

import core.audit
import core.security
from core.domain.advisors import MASKED_HASH
from crud.database_schema import ChecklistProgress, ConferenceChecklist
from crud.db import utcnow

# The password the reveal tests re-authenticate with. Any value works; it is hashed through
# the same `core.security.hash_password` the login route uses.
ADVISOR_PASSWORD = "Advisor!2026"


# --- builders --------------------------------------------------------------------------
#
# Kept local to this file, like `_chair_for` in tests/chair/test_overview.py: only the
# advisor suite needs an advisor that already has a password, or a second school to be
# scoped away from.


def _advisor_with_password(
    factory,
    *,
    identifier: str = "ADV-PW",
    school_name: str = "Password High School",
    password: str = ADVISOR_PASSWORD,
):
    """An advisor account that can pass the credential reveal, plus its school."""
    account = factory.account(
        role="advisor",
        name="Password Advisor",
        identifier=identifier,
        password_hash=core.security.hash_password(password),
    )
    school = factory.school(account, name=school_name)
    return account, school


def _another_school(
    factory, *, name: str = "Rival High School", identifier: str = "ADV-RIVAL"
):
    """A second advisor and school, for the isolation tests."""
    advisor = factory.account(role="advisor", name="Rival Advisor", identifier=identifier)
    school = factory.school(advisor, name=name)
    return advisor, school


def _checklist_item(factory, label: str, position: int = 0) -> ConferenceChecklist:
    item = ConferenceChecklist(label=label, position=position)
    factory.db.add(item)
    factory.db.commit()
    return item


def _tick(factory, school, item: ConferenceChecklist, *, completed: bool = True):
    factory.db.add(
        ChecklistProgress(
            school_id=school.account_id,
            item_id=item.id,
            completed=completed,
            updated_at=utcnow(),
        )
    )
    factory.db.commit()


# The four routes, with a body where one is required. The gate tests are parametrised over
# them so a fifth route cannot ship without the role check.
ADVISOR_ROUTES = [
    ("get", "/api/advisor/delegates", {}),
    ("get", "/api/advisor/delegates/1/paper", {}),
    ("post", "/api/advisor/verify-hashes", {"json": {"password": "irrelevant"}}),
    ("get", "/api/advisor/school", {}),
]


# ---------------------------------------------------------------------------
# Authentication and the role gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", ADVISOR_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    """No token is a 401 with the body shape the frontend reads."""
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", ADVISOR_ROUTES)
def test_every_route_refuses_a_valid_token_of_the_wrong_role(
    client, delegate_headers, method, path, kwargs
):
    """A signed-in delegate is still refused, on every advisor route."""
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# GET /advisor/delegates
# ---------------------------------------------------------------------------


def test_lists_only_the_callers_own_schools_delegates(
    client, factory, advisor_headers, school, committee
):
    """The roster is built from the token's school; a delegate at another school is absent."""
    mine = factory.delegate(
        factory.account(role="delegate", identifier="MINE-1"),
        committee=committee,
        school=school,
        country="France",
    )
    _, rival_school = _another_school(factory)
    factory.delegate(
        factory.account(role="delegate", identifier="RIVAL-1"),
        committee=committee,
        school=rival_school,
        country="Spain",
    )

    response = client.get("/api/advisor/delegates", headers=advisor_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    # `id` is the account id, which is what /delegates/{id}/paper takes back.
    assert body["delegates"][0]["id"] == mine.account_id
    assert body["delegates"][0]["country"] == "France"
    assert [entry["country"] for entry in body["delegates"]] == ["France"]


def test_the_real_hash_never_reaches_the_roster(
    client, factory, advisor_headers, school, committee
):
    """Every hash is masked, and the real value appears nowhere in the response.

    Asserting on ``response.text`` rather than on the one field is deliberate: the JSON is
    readable in devtools whatever the page chooses to render, so a leak anywhere in the body
    is a leak.
    """
    factory.delegate(
        factory.account(role="delegate", identifier="SECRET-HASH-1234"),
        committee=committee,
        school=school,
    )

    response = client.get("/api/advisor/delegates", headers=advisor_headers)

    assert response.json()["delegates"][0]["hash"] == MASKED_HASH
    assert "SECRET-HASH-1234" not in response.text


def test_registered_follows_the_password_hash(
    client, factory, advisor_headers, school, committee
):
    """`registered` is "has this account been claimed", which is a NULL password hash.

    It is what tells the advisor which delegates still need to register before the
    conference, so it is worth pinning both directions.
    """
    factory.delegate(
        factory.account(role="delegate", identifier="UNREG-1"),
        committee=committee,
        school=school,
        country="Argentina",
    )
    factory.delegate(
        factory.account(
            role="delegate",
            identifier="REG-1",
            password_hash=core.security.hash_password("Passw0rd!x"),
        ),
        committee=committee,
        school=school,
        country="France",
    )

    body = client.get("/api/advisor/delegates", headers=advisor_headers).json()

    assert {entry["country"]: entry["registered"] for entry in body["delegates"]} == {
        "Argentina": False,
        "France": True,
    }


def test_the_roster_is_ordered_by_committee_then_country(
    client, factory, advisor_headers, school, committee
):
    """A stable order keeps the roster from reshuffling between two page loads."""
    unsc = factory.committee("UNSC")
    for committee_row, country in (
        (unsc, "France"),
        (committee, "France"),
        (committee, "Argentina"),
    ):
        factory.delegate(
            factory.account(role="delegate"),
            committee=committee_row,
            school=school,
            country=country,
        )

    rows = client.get("/api/advisor/delegates", headers=advisor_headers).json()["delegates"]

    assert [(row["committee"], row["country"]) for row in rows] == [
        ("DISEC", "Argentina"),
        ("DISEC", "France"),
        ("UNSC", "France"),
    ]


def test_the_roster_carries_paper_status_and_grade(
    client, factory, advisor_headers, school, committee
):
    """The advisor's list doubles as a progress tracker, so both fields are in the payload."""
    factory.delegate(
        factory.account(role="delegate", identifier="GRADED-1"),
        committee=committee,
        school=school,
        paper_status="graded",
        paper_grade="18/20",
    )

    entry = client.get("/api/advisor/delegates", headers=advisor_headers).json()["delegates"][0]

    assert entry["paperStatus"] == "graded"
    assert entry["paperGrade"] == "18/20"


def test_the_roster_cannot_be_widened_by_a_query_parameter(
    client, factory, advisor_headers, school, committee
):
    """The school comes from the token; a `school_id` in the URL changes nothing.

    There is no server-side filtering by a client-supplied id to get wrong - which is the
    point of resolving it from the account - but the test pins that a client cannot smuggle
    one in and be obeyed.
    """
    factory.delegate(
        factory.account(role="delegate"), committee=committee, school=school
    )
    _, rival_school = _another_school(factory)
    factory.delegate(
        factory.account(role="delegate"),
        committee=committee,
        school=rival_school,
        country="Spain",
    )

    response = client.get(
        f"/api/advisor/delegates?school_id={rival_school.account_id}",
        headers=advisor_headers,
    )

    assert response.json()["total"] == 1


def test_an_advisor_without_a_school_is_404(client, factory):
    """A token whose account has no school row has nothing to scope to."""
    account = factory.account(role="advisor", identifier="ADV-NO-SCHOOL")

    response = client.get("/api/advisor/delegates", headers=factory.headers(account))

    assert response.status_code == 404
    assert response.json() == {"message": "No school is attached to this account."}


# ---------------------------------------------------------------------------
# GET /advisor/delegates/{id}/paper
# ---------------------------------------------------------------------------


def test_downloads_a_delegates_paper(
    client, factory, advisor_headers, school, committee
):
    """The bytes come back as a PDF under a per-delegate filename."""
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="PAPER-1"),
        committee=committee,
        school=school,
    )
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    response = client.get(
        f"/api/advisor/delegates/{delegate.account_id}/paper", headers=advisor_headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-live"
    assert (
        f"delegate_{delegate.account_id}_paper.pdf"
        in response.headers["content-disposition"]
    )


def test_a_delegate_from_another_school_is_404(
    client, factory, advisor_headers, committee
):
    """A foreign delegate is looked up *within* the caller's school, so it is simply absent."""
    _, rival_school = _another_school(factory)
    foreign = factory.delegate(
        factory.account(role="delegate", identifier="FOREIGN-1"),
        committee=committee,
        school=rival_school,
    )
    factory.upload(foreign, file_path="foreign.pdf", write_bytes=b"%PDF-foreign")

    response = client.get(
        f"/api/advisor/delegates/{foreign.account_id}/paper", headers=advisor_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No such delegate in your school."}


def test_a_nonexistent_delegate_is_indistinguishable_from_a_foreign_one(
    client, advisor_headers
):
    """Both failures carry the same status and the same sentence.

    Distinguishing them would let an advisor probe ids to learn which accounts exist
    elsewhere, so the identical body is the contract, not an accident.
    """
    response = client.get(
        "/api/advisor/delegates/999999/paper", headers=advisor_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No such delegate in your school."}


def test_a_delegate_who_never_submitted_is_404(
    client, factory, advisor_headers, school, committee
):
    """Nothing submitted is its own message: there is no file to be missing."""
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="NOPAPER-1"),
        committee=committee,
        school=school,
    )

    response = client.get(
        f"/api/advisor/delegates/{delegate.account_id}/paper", headers=advisor_headers
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "No position paper has been submitted yet."
    }


def test_a_row_whose_file_is_gone_is_a_different_404(
    client, factory, advisor_headers, school, committee, papers_dir
):
    """A row without bytes is "missing", not "never submitted" - the advisor can act on it."""
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="GONE-1"),
        committee=committee,
        school=school,
    )
    factory.upload(delegate, file_path="gone.pdf", write_bytes=b"%PDF-gone")
    (papers_dir / "gone.pdf").unlink()

    response = client.get(
        f"/api/advisor/delegates/{delegate.account_id}/paper", headers=advisor_headers
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "The stored file is missing. The paper has to be uploaded again."
    }


def test_the_newest_paper_is_the_one_served(
    client, factory, advisor_headers, school, committee
):
    """The advisor reads the same "paper in force" the delegate sees."""
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="NEWEST-1"),
        committee=committee,
        school=school,
    )
    factory.upload(delegate, when=utcnow(), file_path="old.pdf", write_bytes=b"%PDF-old")
    factory.upload(delegate, when=utcnow(), file_path="new.pdf", write_bytes=b"%PDF-new")

    response = client.get(
        f"/api/advisor/delegates/{delegate.account_id}/paper", headers=advisor_headers
    )

    assert response.content == b"%PDF-new"


def test_an_advisor_without_a_school_cannot_download(
    client, factory, committee, school
):
    """The school is resolved before the delegate, so the failure names the real problem."""
    account = factory.account(role="advisor", identifier="ADV-NO-SCHOOL-2")
    delegate = factory.delegate(
        factory.account(role="delegate", identifier="SOME-1"),
        committee=committee,
        school=school,
    )

    response = client.get(
        f"/api/advisor/delegates/{delegate.account_id}/paper",
        headers=factory.headers(account),
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No school is attached to this account."}


# ---------------------------------------------------------------------------
# POST /advisor/verify-hashes
# ---------------------------------------------------------------------------


def test_the_right_password_reveals_the_real_hashes(client, factory, committee):
    """Re-authentication turns the masked roster back into the real access codes."""
    advisor, school = _advisor_with_password(factory, identifier="ADV-REVEAL")
    factory.delegate(
        factory.account(role="delegate", identifier="REVEAL-ME-1"),
        committee=committee,
        school=school,
    )

    response = client.post(
        "/api/advisor/verify-hashes",
        headers=factory.headers(advisor),
        json={"password": ADVISOR_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["delegates"][0]["hash"] == "REVEAL-ME-1"


def test_a_wrong_password_is_403_and_keeps_the_session(client, factory):
    """403, not 401: a 401 would make the client log the advisor out mid-modal.

    They are still signed in - they just did not re-prove who they are - so the message has
    to reach the modal rather than the login screen.
    """
    advisor, _ = _advisor_with_password(factory, identifier="ADV-WRONG")

    response = client.post(
        "/api/advisor/verify-hashes",
        headers=factory.headers(advisor),
        json={"password": "not-the-password"},
    )

    assert response.status_code == 403
    assert response.json() == {"message": "Incorrect password. Access denied."}


def test_an_unclaimed_account_cannot_reveal(client, advisor_headers):
    """The default advisor fixture has no password hash, so nothing can match it.

    ``verify_password`` returns False for a NULL hash rather than raising, which is what
    keeps this a clean 403.
    """
    response = client.post(
        "/api/advisor/verify-hashes", headers=advisor_headers, json={"password": ""}
    )

    assert response.status_code == 403
    assert response.json() == {"message": "Incorrect password. Access denied."}


def test_a_missing_password_field_is_refused_without_a_crash(client, advisor_headers):
    """`password` is optional in the model, so the endpoint sees "" and rejects it as wrong.

    A 422 here would be defensible too, but the current contract is a password failure - and
    the point of the test is that an absent field never becomes a 500.
    """
    response = client.post(
        "/api/advisor/verify-hashes", headers=advisor_headers, json={}
    )

    assert response.status_code == 403
    assert response.json() == {"message": "Incorrect password. Access denied."}


def test_an_over_long_password_is_a_422_with_a_readable_sentence(
    client, advisor_headers
):
    """Pydantic's limit is what stops Argon2 being handed a megabyte to hash.

    The message goes straight into a toast, so it is the friendly form rather than
    ``body.password: String should have at most 200 characters``.
    """
    response = client.post(
        "/api/advisor/verify-hashes",
        headers=advisor_headers,
        json={"password": "x" * 300},
    )

    assert response.status_code == 422
    assert response.json() == {"message": "Password must be at most 200 characters."}


def test_the_reveal_is_scoped_to_the_callers_school(client, factory, committee):
    """A successful reveal returns this school's hashes and nobody else's."""
    advisor, school = _advisor_with_password(
        factory, identifier="ADV-SCOPE", school_name="Scope High School"
    )
    factory.delegate(
        factory.account(role="delegate", identifier="MINE-1"),
        committee=committee,
        school=school,
    )
    _, rival_school = _another_school(factory)
    factory.delegate(
        factory.account(role="delegate", identifier="THEIRS-1"),
        committee=committee,
        school=rival_school,
    )

    body = client.post(
        "/api/advisor/verify-hashes",
        headers=factory.headers(advisor),
        json={"password": ADVISOR_PASSWORD},
    ).json()

    assert [entry["hash"] for entry in body["delegates"]] == ["MINE-1"]


def test_a_successful_reveal_is_written_to_the_technical_log(client, factory, committee):
    """Handing over a school's real access codes is a credential event.

    The school name is unique to this test because the log file accumulates for the whole
    session - an assertion on ``hashes.revealed`` alone would pass on another test's line.
    """
    advisor, school = _advisor_with_password(
        factory, identifier="ADV-AUDIT", school_name="Audit High School"
    )
    factory.delegate(
        factory.account(role="delegate", identifier="AUD-1"),
        committee=committee,
        school=school,
    )

    client.post(
        "/api/advisor/verify-hashes",
        headers=factory.headers(advisor),
        json={"password": ADVISOR_PASSWORD},
    )

    line = core.audit.read("technical")
    assert "hashes.revealed" in line
    assert 'school="Audit High School"' in line
    assert "count=1" in line


def test_a_failed_reveal_writes_no_audit_line(client, factory):
    """A wrong password is a rejected attempt, not a credential event."""
    advisor, _ = _advisor_with_password(factory, identifier="ADV-NOAUDIT")
    before = core.audit.read("technical")

    client.post(
        "/api/advisor/verify-hashes",
        headers=factory.headers(advisor),
        json={"password": "wrong"},
    )

    assert "hashes.revealed" not in core.audit.read("technical")[len(before):]


# ---------------------------------------------------------------------------
# GET /advisor/school
# ---------------------------------------------------------------------------


def test_the_overview_returns_the_school_details(client, advisor_headers):
    """Field names follow the frontend contract, not the columns.

    ``school_name`` becomes ``name``, ``zip_code`` becomes ``zip``, ``invoiceURL`` becomes
    ``invoiceUrl`` - a rename here silently blanks a field on the page.
    """
    body = client.get("/api/advisor/school", headers=advisor_headers).json()

    assert body["school"] == {
        "name": "Test High School",
        "address": "1 Test Way",
        "city": "Testville",
        "state": "CA",
        "zip": "90000",
        "advisorName": "Advisor Person",
        "advisorEmail": "advisor@example.test",
        "advisorPhone": "555-0100",
        "headDelegateName": "Head Delegate",
        "headDelegateEmail": "head@example.test",
        "headDelegatePhone": "555-0101",
    }


def test_billing_reports_the_invoice_url_and_payment_status(
    client, db, advisor_headers, school
):
    """Both billing fields are optional in the column, so both fallbacks are exercised."""
    school.invoiceURL = "https://example.test/invoice.pdf"
    school.payment_status = "partially paid"
    db.commit()

    body = client.get("/api/advisor/school", headers=advisor_headers).json()

    assert body["billing"] == {
        "invoiceUrl": "https://example.test/invoice.pdf",
        "paymentStatus": "partially paid",
    }


def test_an_absent_invoice_url_is_an_empty_string(
    client, db, advisor_headers, school
):
    """The column is nullable; the payload is not, because the frontend binds it to an href."""
    school.invoiceURL = None
    school.payment_status = "unpaid"
    db.commit()

    billing = client.get("/api/advisor/school", headers=advisor_headers).json()["billing"]

    assert billing == {"invoiceUrl": "", "paymentStatus": "unpaid"}


def test_the_checklist_is_shared_and_ordered_by_position(
    client, factory, advisor_headers
):
    """Labels are conference-wide; the order is the admin's explicit ``position``."""
    _checklist_item(factory, "Pay the conference fee", position=2)
    _checklist_item(factory, "Submit position papers", position=1)
    _checklist_item(factory, "Book travel", position=3)

    checklist = client.get("/api/advisor/school", headers=advisor_headers).json()["checklist"]

    assert [item["label"] for item in checklist] == [
        "Submit position papers",
        "Pay the conference fee",
        "Book travel",
    ]


def test_ticks_are_per_school(client, factory, advisor_headers, school):
    """The isolation rule again, on the checklist: a rival's tick must not show.

    One label is ticked by this school and a different one by the rival, so a missing school
    filter would light up the wrong row rather than merely duplicating one.
    """
    fee = _checklist_item(factory, "Pay the conference fee", position=1)
    travel = _checklist_item(factory, "Book travel", position=2)
    _tick(factory, school, fee)

    _, rival_school = _another_school(factory)
    _tick(factory, rival_school, travel)

    checklist = client.get("/api/advisor/school", headers=advisor_headers).json()["checklist"]

    assert checklist == [
        {"label": "Pay the conference fee", "completed": True},
        {"label": "Book travel", "completed": False},
    ]


def test_an_item_with_no_progress_row_reads_as_not_done(
    client, factory, advisor_headers
):
    """The progress table only holds ticks; absence is the normal "not done" state."""
    _checklist_item(factory, "Pay the conference fee")

    checklist = client.get("/api/advisor/school", headers=advisor_headers).json()["checklist"]

    assert checklist == [{"label": "Pay the conference fee", "completed": False}]


def test_an_explicitly_cleared_tick_reads_as_not_done(
    client, factory, advisor_headers, school
):
    """A cleared box is a stored ``False``, not a deleted row - both must read the same."""
    item = _checklist_item(factory, "Pay the conference fee")
    _tick(factory, school, item, completed=False)

    checklist = client.get("/api/advisor/school", headers=advisor_headers).json()["checklist"]

    assert checklist == [{"label": "Pay the conference fee", "completed": False}]


def test_a_school_with_no_checklist_lines_gets_an_empty_list(
    client, advisor_headers
):
    """Before an admin writes the checklist, the panel renders nothing rather than failing."""
    body = client.get("/api/advisor/school", headers=advisor_headers).json()

    assert body["checklist"] == []


def test_an_advisor_without_a_school_is_404_on_the_overview(client, factory):
    account = factory.account(role="advisor", identifier="ADV-NO-SCHOOL-3")

    response = client.get("/api/advisor/school", headers=factory.headers(account))

    assert response.status_code == 404
    assert response.json() == {"message": "No school is attached to this account."}
