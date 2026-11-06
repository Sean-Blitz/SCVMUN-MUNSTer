"""End-to-end tests for the delegate endpoints, driven through Starlette's TestClient.

These are *API* tests, not domain tests. Everything below goes over HTTP: the bearer token,
the role gate, multipart parsing, the status code, and the ``{"message": ...}`` body the
frontend renders in a toast. That is the layer these tests exist to protect - the domain
rules themselves are cheaper to test directly, without a client.

Each test is written to fail for one reason, so a CI failure reads like a sentence.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/test_delegates_endpoints.py -v

Prerequisites: a running PostgreSQL, and a ``DATABASE_URL`` in ``Backend/crud/.env``. The
``conftest.py`` next to this file derives a ``<name>_test`` database from it, creates that
database if needed, and refuses to run against a name that does not contain "test".
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

import core.storage
from core import controls
from core.domain import delegates as delegates_domain
from crud.database_schema import Uploads
from crud.db import utcnow

# A minimal file that passes the ``%PDF-`` signature check the domain performs. Tests that
# care about the bytes read them back and compare.
PDF_BYTES = b"%PDF-1.4\n% test paper\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def pdf_upload(name: str = "position-paper.pdf", content: bytes = PDF_BYTES):
    """The ``files=`` argument for a multipart PDF upload."""
    return {"paper": (name, content, "application/pdf")}


# The three routes that make up /delegate/*, with a body where one is required. The two gate
# tests below are parametrised over this list, so a fourth route cannot quietly ship
# without the role check.
DELEGATE_ROUTES = [
    ("get", "/api/delegate/my-assignment", {}),
    ("get", "/api/delegate/my-paper", {}),
    ("post", "/api/delegate/upload-paper", {"files": pdf_upload()}),
]


# ---------------------------------------------------------------------------
# Authentication and the role gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", DELEGATE_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    """No token at all is a 401, with the body shape the frontend expects.

    A 401 rather than FastAPI's default 403 for a missing bearer token matters: the axios
    interceptor treats 401 as "log out and go to /", so this message is what a delegate
    reads after being bounced to the login screen.
    """
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", DELEGATE_ROUTES)
def test_every_route_refuses_a_valid_token_of_the_wrong_role(
    client, advisor_headers, method, path, kwargs
):
    """A real, unexpired token belonging to an advisor is still refused.

    The gate is the router-wide ``require_roles("delegate")``, so one test covers all three
    routes. Worth separating from the 401 above: being *logged in* and being *allowed* are
    different failures, and only one of them should log you out.
    """
    response = getattr(client, method)(path, headers=advisor_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


def test_an_unknown_token_is_rejected(client):
    """A made-up bearer token is a 401, not a 500 and not a pass."""
    response = client.get(
        "/api/delegate/my-assignment",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"message": "Invalid or expired session token."}


def test_an_expired_session_is_rejected(client, factory):
    """Expiry is enforced on the way in, without a cleanup job deleting the row.

    The session row deliberately stays in the table: an expired row must not authenticate,
    and deleting it on the way through would turn every read into a write.
    """
    account = factory.account(role="delegate", identifier="EXPIRED-1")
    headers = factory.headers(account, lifetime=timedelta(seconds=-1))

    response = client.get("/api/delegate/my-assignment", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"message": "Invalid or expired session token."}


# ---------------------------------------------------------------------------
# GET /delegate/my-assignment
# ---------------------------------------------------------------------------


def test_returns_the_dashboard_payload(client, delegate, delegate_headers):
    """The happy path: committee, country, and an empty paper panel.

    The dashboard renders itself from this response, so these field names are the contract
    with ``DelegateDashboardView.vue``.
    """
    response = client.get("/api/delegate/my-assignment", headers=delegate_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["delegate"] == {"committee": "DISEC", "country": "France"}
    assert body["announcements"] == []
    assert body["conferenceLinks"] == []
    assert body["positionPaper"]["status"] == "unsubmitted"
    assert body["positionPaper"]["criteria"] == []


def test_an_account_without_a_delegate_profile_is_404(client, factory):
    """A token for an account that never got a delegate row fails cleanly.

    This is the half-created account: the admin minted a hash but never assigned a
    committee, so there is nothing to render. The endpoint turns the domain's "no profile"
    into an actionable 404 rather than an empty dashboard.
    """
    orphan = factory.account(role="delegate", identifier="ORPHAN-1")
    headers = factory.headers(orphan)

    response = client.get("/api/delegate/my-assignment", headers=headers)

    assert response.status_code == 404
    assert response.json() == {
        "message": "No delegate profile is attached to this account."
    }


def test_announcements_respect_committee_and_schedule_window(
    client, factory, committee, delegate, delegate_headers
):
    """Only live lines addressed to this delegate come back, general lines first.

    Four cases are separated here: a global line (everyone), a line for this committee, a
    line for a different committee, and two lines outside their schedule window. The
    ordering assertion also pins the documented rule that general lines sort ahead of
    committee ones even when their ``position`` is higher.
    """
    other_committee = factory.committee("UNSC")
    factory.broadcast(body="general live", position=5)
    factory.broadcast(body="DISEC line", committee=committee, position=0)
    factory.broadcast(body="UNSC line", committee=other_committee)
    factory.broadcast(body="already over", ends_at=utcnow() - timedelta(days=1))
    factory.broadcast(body="not started", starts_at=utcnow() + timedelta(days=1))

    response = client.get("/api/delegate/my-assignment", headers=delegate_headers)

    assert response.status_code == 200
    assert response.json()["announcements"] == ["general live", "DISEC line"]


def test_conference_links_come_from_link_broadcasts(
    client, factory, delegate, delegate_headers
):
    """Links are a strip of their own, separate from announcements, and carry a url."""
    factory.broadcast(
        kind="link", body="Delegate handbook", url="https://example.test/hb"
    )
    factory.broadcast(kind="announcement", body="Not a link")

    response = client.get("/api/delegate/my-assignment", headers=delegate_headers)

    assert response.json()["conferenceLinks"] == [
        {"text": "Delegate handbook", "url": "https://example.test/hb"}
    ]
    assert response.json()["announcements"] == ["Not a link"]


def test_a_graded_paper_exposes_its_rubric_breakdown(
    client, db, delegate, delegate_headers, monkeypatch
):
    """A graded paper joins the chair's stored marks with the rubric labels.

    A delegate cannot call /chair/rubric (it is role-gated), so the labels have to be
    resolved inside this response. ``controls.paper_rubric_data`` is replaced through
    monkeypatch because it is module-level mutable state - pytest restores it afterwards,
    which is precisely the leak this kind of global would otherwise cause.

    Note the keys: JSONB object keys are always strings, so ``{"1": 7.5}`` has to match a
    rubric whose criterion id is the integer ``1``. Criterion 3 is left unmarked and must be
    omitted rather than reported as a zero.
    """
    monkeypatch.setattr(
        controls,
        "paper_rubric_data",
        [
            {"id": 1, "label": "Clarity", "maxScore": 10},
            {"id": 2, "label": "Evidence", "maxScore": 10},
            {"id": 3, "label": "Never marked", "maxScore": 5},
        ],
    )

    delegate.paper_status = "graded"
    delegate.paper_grade = "15/20"
    delegate.paper_comments = "Solid work."
    delegate.paper_rubric_grade = {"1": 7.5, "2": 7.5}
    db.commit()

    response = client.get("/api/delegate/my-assignment", headers=delegate_headers)

    paper = response.json()["positionPaper"]
    assert paper["status"] == "graded"
    assert paper["score"] == "15/20"
    assert paper["feedback"] == "Solid work."
    assert paper["criteria"] == [
        {"id": 1, "label": "Clarity", "score": 7.5, "maxScore": 10.0},
        {"id": 2, "label": "Evidence", "score": 7.5, "maxScore": 10.0},
    ]


def test_a_submitted_paper_hides_the_breakdown(
    client, db, delegate, delegate_headers, monkeypatch
):
    """Marks that exist before the grade is published are not revealed.

    The chair may have started marking; until the status is "graded" the panel shows a
    waiting message and the criteria list stays empty.
    """
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": 1, "label": "Clarity", "maxScore": 10}]
    )

    delegate.paper_status = "submitted"
    delegate.paper_rubric_grade = {"1": 9}
    db.commit()

    response = client.get("/api/delegate/my-assignment", headers=delegate_headers)

    assert response.json()["positionPaper"]["criteria"] == []


# ---------------------------------------------------------------------------
# POST /delegate/upload-paper
# ---------------------------------------------------------------------------


def test_uploading_stores_the_pdf_and_marks_the_paper_submitted(
    client, db, delegate, delegate_headers, papers_dir
):
    """The happy path: 201, one row, one file, and the delegate's status flipped.

    ``db.expire_all()`` matters. The test's session cached ``delegate`` when the fixture
    built it; the request updated that row in a *different* session, so the cached object is
    stale until it is expired and reloaded.
    """
    response = client.post(
        "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
    )

    assert response.status_code == 201
    assert response.json() == {
        "message": "Position paper received.",
        "file_name": "position-paper.pdf",
        "status": "submitted",
    }

    db.expire_all()
    rows = db.scalars(select(Uploads)).all()
    assert len(rows) == 1
    assert delegate.paper_status == "submitted"

    stored = papers_dir / rows[0].file_path
    assert stored.read_bytes() == PDF_BYTES


def test_a_file_without_a_pdf_signature_is_rejected(client, delegate_headers, papers_dir):
    """A .pdf name and a PDF content type are only claims; the bytes decide.

    This passes the endpoint's transport check (the filename ends in .pdf) and is caught by
    the domain's ``%PDF-`` signature check, which is the point: the two layers do different
    jobs. Nothing may reach the disk.
    """
    response = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files={"paper": ("paper.pdf", b"this is plain text", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "That file is not a PDF."}
    assert list(papers_dir.iterdir()) == []


def test_a_file_that_does_not_claim_to_be_a_pdf_is_rejected(client, delegate_headers):
    """Neither the extension nor the content type says PDF, so it is a 400 before reading.

    A different message from the signature failure above: this one is decided from the
    multipart metadata, without reading the body, and it tells the delegate what to fix.
    """
    response = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files={"paper": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Only a PDF position paper can be uploaded."}


def test_an_oversized_pdf_is_413(client, delegate_headers, monkeypatch, papers_dir):
    """The 413 carries the limit the delegate actually exceeded.

    ``MAX_PAPER_BYTES`` is lowered instead of generating 10 MB, so the test stays fast and
    the message stays meaningful ("larger than 2 MB"). nginx allows a 12m body on this
    route precisely so the app gets to answer this way instead of with nginx's own HTML 413.
    """
    monkeypatch.setattr(core.storage, "MAX_PAPER_BYTES", 2 * 1024 * 1024)
    oversized = b"%PDF-1.4\n" + b"x" * (2 * 1024 * 1024)

    response = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(content=oversized),
    )

    assert response.status_code == 413
    assert response.json() == {"message": "The PDF is larger than 2 MB."}
    assert list(papers_dir.iterdir()) == []


def test_a_graded_paper_cannot_be_replaced(client, db, delegate, delegate_headers):
    """Once a chair has graded the paper, uploading again is a 409, not a silent overwrite.

    A conflict rather than a 400: the request is well formed, it just cannot be honoured in
    the paper's current state - and a 401 here would bounce the user to the login screen.
    """
    delegate.paper_status = "graded"
    db.commit()

    response = client.post(
        "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
    )

    assert response.status_code == 409
    assert response.json() == {
        "message": "This paper has already been graded and cannot be replaced."
    }


def test_uploading_is_rate_limited_after_five_attempts(client, delegate_headers):
    """The sixth upload in an hour is refused, with a Retry-After the client can use.

    Replacing a paper is allowed until it is graded, so without this cap a single valid
    token could churn the disk. The cap counts stored rows rather than files: every upload
    is one row, and only the newest file is kept.
    """
    for attempt in range(controls.MAX_UPLOADS_PER_HOUR):
        allowed = client.post(
            "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
        )
        assert allowed.status_code == 201, f"upload {attempt + 1} should be accepted"

    denied = client.post(
        "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
    )

    limit = controls.MAX_UPLOADS_PER_HOUR
    window = delegates_domain.UPLOAD_WINDOW_HOURS
    unit = "time" if limit == 1 else "times"
    hours = "hour" if window == 1 else f"{window} hours"

    assert denied.status_code == 429
    assert denied.json() == {
        "message": f"You can upload a position paper at most {limit} {unit} per {hours}."
    }
    # The header lets the client back off without guessing.
    assert denied.headers["Retry-After"] == str(window * 3600)


def test_re_uploading_leaves_exactly_one_file_on_disk(
    client, delegate_headers, papers_dir
):
    """Rows are append-only history, but only the live paper's bytes survive.

    Two uploads, two rows, one file. Without the prune step a delegate could fill the volume
    by uploading repeatedly - every attempt is allowed until the paper is graded.
    """
    first = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(content=b"%PDF-1.4\nfirst\n%%EOF\n"),
    )
    second = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(content=b"%PDF-1.4\nsecond\n%%EOF\n"),
    )

    assert first.status_code == 201
    assert second.status_code == 201

    files = [path for path in papers_dir.iterdir() if path.is_file()]
    assert len(files) == 1
    assert files[0].read_bytes() == b"%PDF-1.4\nsecond\n%%EOF\n"


def test_the_client_filename_cannot_escape_the_upload_directory(
    client, delegate_headers, papers_dir
):
    """A path in the filename is stripped to its basename before it is stored.

    The stored *file* is always a generated name; this covers the display name kept for the
    chair's inbox, which is the one place client input survives.
    """
    response = client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(name="../../etc/passwd.pdf"),
    )

    assert response.status_code == 201
    assert response.json()["file_name"] == "passwd.pdf"
    assert [path for path in papers_dir.iterdir() if path.is_file()]


# ---------------------------------------------------------------------------
# GET /delegate/my-paper
# ---------------------------------------------------------------------------


def test_downloading_before_uploading_is_404(client, delegate_headers):
    """No submission yet is a 404 with a message the delegate can act on."""
    response = client.get("/api/delegate/my-paper", headers=delegate_headers)

    assert response.status_code == 404
    assert response.json() == {"message": "No position paper has been submitted yet."}


def test_a_stored_paper_is_served_as_a_pdf_named_after_the_country(
    client, delegate_headers
):
    """The response returns the bytes, the PDF media type, and a readable filename.

    The download is scoped by the token rather than by a path parameter, which is why there
    is no id in the URL to tamper with.
    """
    client.post(
        "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
    )

    response = client.get("/api/delegate/my-paper", headers=delegate_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == PDF_BYTES
    assert "France_Position_Paper.pdf" in response.headers["content-disposition"]


def test_a_row_whose_file_disappeared_is_404_not_500(
    client, delegate_headers, papers_dir
):
    """A missing file on disk is a missing paper, not a crash.

    This is what a half-restored volume looks like: the database says a paper exists and the
    filesystem disagrees. The delegate can fix it by uploading again, so the message says so.
    """
    client.post(
        "/api/delegate/upload-paper", headers=delegate_headers, files=pdf_upload()
    )
    for stored in papers_dir.iterdir():
        if stored.is_file():
            stored.unlink()

    response = client.get("/api/delegate/my-paper", headers=delegate_headers)

    assert response.status_code == 404
    assert response.json() == {
        "message": "The stored file is missing. The paper has to be uploaded again."
    }


def test_the_newest_paper_is_the_one_served(client, delegate_headers):
    """Re-uploading changes what a download returns.

    Both the download and /my-assignment resolve "the paper in force" the same way - newest
    row, with ``upload_id`` breaking a timestamp tie - so this pins that the two views
    cannot disagree.
    """
    newer = b"%PDF-1.4\nthe replacement\n%%EOF\n"
    client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(content=b"%PDF-1.4\nthe original\n%%EOF\n"),
    )
    client.post(
        "/api/delegate/upload-paper",
        headers=delegate_headers,
        files=pdf_upload(content=newer),
    )

    response = client.get("/api/delegate/my-paper", headers=delegate_headers)

    assert response.status_code == 200
    assert response.content == newer
