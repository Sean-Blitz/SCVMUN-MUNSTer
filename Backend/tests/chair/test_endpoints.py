"""API tests for /chair/*, driven through Starlette's TestClient.

The chair surface is the largest in the API: a committee overview, a paper-grading workflow,
a paper download, and an awards workflow, nine routes in all. What they share is *committee
scoping* - every write resolves the chair's committee from the token, and a delegate from
another committee answers 404 exactly as an unknown id does.

Three contract details are pinned here because each is one refactor away from silently
changing the frontend's behaviour:

* a delegate who has not submitted is **409 when grading** but **404 when downloading** - the
  same domain condition, two different messages;
* the stored totals are **recomputed from the marks**, so the ``totalScore`` in the body is
  ignored (a client cannot put a wrong number in front of a chair);
* ``GET /chair/rubric`` and the two awards read routes work for an **admin** as well as a
  chair - admins have no ``chairs`` row, so only the routes that look one up fail for them.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/chair/test_endpoints.py -v
"""

from datetime import datetime

import pytest

import core.security
from core import controls
from crud.database_schema import Rubric, TimelineEvent
from crud.db import utcnow

# Two rubric documents, in the shapes core/domain/rubrics.py publishes.
PAPER_RUBRIC = [
    {"id": "clarity", "label": "Clarity", "maxScore": 10},
    {"id": "evidence", "label": "Evidence", "maxScore": 5},
    {"id": "style", "label": "Style", "maxScore": 5},
]

AWARDS_RUBRIC = [
    {
        "id": "speaking",
        "label": "Speaking",
        "levels": [
            {"score": 4, "label": "Excellent", "description": "Commanding"},
            {"score": 2, "label": "Developing"},
        ],
    },
    {"id": "diplomacy", "label": "Diplomacy", "levels": [{"score": 3, "label": "Strong"}]},
]

# The nine routes, with a body where one is required, for the gate tests.
CHAIR_ROUTES = [
    ("get", "/api/chair/committee/overview", {}),
    ("get", "/api/chair/rubric", {}),
    ("get", "/api/chair/delegates", {}),
    (
        "post",
        "/api/chair/papers/1/grade",
        {"json": {"delegateId": 1, "scores": {}, "totalScore": "0/0"}},
    ),
    ("get", "/api/chair/papers/1/download", {}),
    ("get", "/api/chair/awards/options", {}),
    ("get", "/api/chair/awards/rubric", {}),
    ("get", "/api/chair/awards/delegates", {}),
    (
        "post",
        "/api/chair/awards/1",
        {
            "json": {
                "delegateId": 1,
                "assignedAward": "Best Delegate",
                "scores": {},
                "totalScore": 0,
            }
        },
    ),
]


# --- builders --------------------------------------------------------------------------


def _save_rubric(factory, kind: str, items: list[dict]) -> None:
    """Store a rubric document the way PUT /admin/rubrics does."""
    factory.db.add(Rubric(kind=kind, items=items, updated_at=utcnow(), updated_by="admin:1"))
    factory.db.commit()


def _delegate_in(factory, committee, school, *, country="France", **fields):
    """A delegate account plus its profile, in the given committee and school."""
    return factory.delegate(
        factory.account(role="delegate"),
        committee=committee,
        school=school,
        country=country,
        **fields,
    )


def _other_committee(factory, name: str = "UNSC"):
    return factory.committee(name)


# ---------------------------------------------------------------------------
# Authentication and the role gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", CHAIR_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", CHAIR_ROUTES)
def test_every_route_refuses_a_valid_token_of_the_wrong_role(
    client, delegate_headers, method, path, kwargs
):
    """A delegate token is refused on every chair route."""
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


def test_an_admin_passes_the_gate_but_has_no_chair_profile(client, factory):
    """Admins reach the chair views (the Vue router allows it), and that asymmetry shows.

    The rubric and awards reads need no ``chairs`` row, so they answer 200. The roster does
    resolve one, so it answers 404 - not 403, because the admin *is* allowed in.
    """
    admin = factory.account(role="admin", name="Admin Person", identifier="ADMIN-1")
    headers = factory.headers(admin)

    assert client.get("/api/chair/rubric", headers=headers).status_code == 200
    assert client.get("/api/chair/awards/options", headers=headers).status_code == 200

    roster = client.get("/api/chair/delegates", headers=headers)
    assert roster.status_code == 404
    assert roster.json() == {"message": "No chair profile is attached to this account."}


# ---------------------------------------------------------------------------
# GET /chair/committee/overview
# ---------------------------------------------------------------------------


def test_the_overview_counts_only_the_chairs_own_committee(
    client, factory, chair_headers, committee, school
):
    """Four counters, all scoped by committee; a graded paper counts as submitted too.

    The rival committee's graded delegate is the control: if the scoping regressed, every
    count below would be one higher.
    """
    registered = factory.account(
        role="delegate", password_hash=core.security.hash_password("Passw0rd!x")
    )
    factory.delegate(registered, committee=committee, school=school, country="Argentina",
                     paper_status="submitted")
    _delegate_in(factory, committee, school, country="France", paper_status="graded")
    _delegate_in(factory, committee, school, country="Spain", paper_status="unsubmitted")

    rival = _other_committee(factory)
    _delegate_in(factory, rival, school, country="Italy", paper_status="graded")

    body = client.get("/api/chair/committee/overview", headers=chair_headers).json()

    assert body["totalDelegates"] == 3
    assert body["delegatesRegistered"] == 1
    assert body["papersGraded"] == 1
    assert body["totalPapersSubmitted"] == 2
    assert body["chairName"] == "Chair Person"
    assert body["committeeName"] == "DISEC"


def test_the_timeline_is_split_by_phase_and_sorted_by_time(
    client, factory, chair_headers
):
    """Events are points in time per phase; the frontend compares them with the clock.

    Out-of-order insertion proves the sort, and the ``+00:00`` offset proves the timestamp
    is unambiguous - a bare naive value would be read as *local* time by `new Date(...)`.
    """
    factory.db.add_all(
        [
            TimelineEvent(
                phase="preConference", label="Second", starts_at=datetime(2027, 1, 1, 9, 0)
            ),
            TimelineEvent(
                phase="duringConference", label="Conference", starts_at=datetime(2027, 2, 1)
            ),
            TimelineEvent(
                phase="preConference", label="First", starts_at=datetime(2026, 12, 1, 9, 0)
            ),
        ]
    )
    factory.db.commit()

    timeline = client.get("/api/chair/committee/overview", headers=chair_headers).json()[
        "timeline"
    ]

    assert timeline["preConference"] == [
        {"label": "First", "timestamp": "2026-12-01T09:00:00+00:00"},
        {"label": "Second", "timestamp": "2027-01-01T09:00:00+00:00"},
    ]
    assert timeline["duringConference"] == [
        {"label": "Conference", "timestamp": "2027-02-01T00:00:00+00:00"}
    ]


def test_both_timeline_phases_are_present_even_when_empty(client, chair_headers):
    """The template iterates both keys directly, so neither may be missing."""
    body = client.get("/api/chair/committee/overview", headers=chair_headers).json()

    assert body["timeline"] == {"preConference": [], "duringConference": []}


def test_an_account_without_a_chair_profile_is_404_on_the_overview(client, factory):
    account = factory.account(role="chair", identifier="CHAIR-NO-PROFILE")

    response = client.get(
        "/api/chair/committee/overview", headers=factory.headers(account)
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No chair profile is attached to this account."}


# ---------------------------------------------------------------------------
# GET /chair/rubric
# ---------------------------------------------------------------------------


def test_the_paper_rubric_is_empty_until_an_admin_saves_one(client, chair_headers):
    """A fresh conference has no stored rubric; the view must render an empty editor."""
    assert client.get("/api/chair/rubric", headers=chair_headers).json() == []


def test_a_stored_paper_rubric_is_published(client, factory, chair_headers):
    _save_rubric(factory, "paper", PAPER_RUBRIC)

    body = client.get("/api/chair/rubric", headers=chair_headers).json()

    assert body == [
        {"id": "clarity", "label": "Clarity", "maxScore": 10.0},
        {"id": "evidence", "label": "Evidence", "maxScore": 5.0},
        {"id": "style", "label": "Style", "maxScore": 5.0},
    ]


def test_a_criterion_without_an_id_is_skipped(client, factory, chair_headers):
    """The id keys every stored mark, so an id-less criterion could never be graded."""
    _save_rubric(
        factory,
        "paper",
        [{"label": "No id", "maxScore": 5}, {"id": "ok", "label": "Ok", "maxScore": 3}],
    )

    body = client.get("/api/chair/rubric", headers=chair_headers).json()

    assert [criterion["id"] for criterion in body] == ["ok"]


def test_a_criterion_without_a_label_or_a_max_falls_back(client, factory, chair_headers):
    """Both fallbacks matter: a blank label renders nothing, and a missing max would break
    the ``0..max`` validation in the grading screen."""
    _save_rubric(factory, "paper", [{"id": "bare"}])

    assert client.get("/api/chair/rubric", headers=chair_headers).json() == [
        {"id": "bare", "label": "bare", "maxScore": 0.0}
    ]


# ---------------------------------------------------------------------------
# GET /chair/delegates
# ---------------------------------------------------------------------------


def test_the_roster_lists_the_committees_delegates_ordered_by_country(
    client, factory, chair_headers, committee, school
):
    for country in ("Spain", "Argentina"):
        _delegate_in(factory, committee, school, country=country)
    _delegate_in(factory, _other_committee(factory), school, country="France")

    body = client.get("/api/chair/delegates", headers=chair_headers).json()

    assert [entry["country"] for entry in body] == ["Argentina", "Spain"]


def test_the_roster_reports_grading_state(client, factory, chair_headers, committee, school):
    delegate = _delegate_in(
        factory,
        committee,
        school,
        paper_status="graded",
        paper_grade="18/20",
        paper_rubric_grade={"clarity": 10, "evidence": 8},
        paper_comments="Strong opening.",
    )

    entry = client.get("/api/chair/delegates", headers=chair_headers).json()[0]

    assert entry == {
        "id": delegate.account_id,
        "country": "France",
        "committee": "DISEC",
        "status": "graded",
        "submissionDate": "",
        "totalScore": "18/20",
        "scores": {"clarity": 10.0, "evidence": 8.0},
        "comments": "Strong opening.",
    }


def test_the_submission_date_is_the_newest_upload_with_a_utc_offset(
    client, factory, chair_headers, committee, school
):
    """Naive-UTC columns are rendered with an explicit offset, newest upload wins."""
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")
    factory.upload(delegate, when=datetime(2026, 10, 4, 9, 0), file_path="old.pdf")
    factory.upload(delegate, when=datetime(2026, 10, 5, 9, 30), file_path="new.pdf")

    entry = client.get("/api/chair/delegates", headers=chair_headers).json()[0]

    assert entry["submissionDate"] == "2026-10-05T09:30:00+00:00"


def test_a_delegate_who_never_uploaded_has_an_empty_submission_date(
    client, factory, chair_headers, committee, school
):
    """Empty string, not null: the view prints it as-is."""
    _delegate_in(factory, committee, school)

    entry = client.get("/api/chair/delegates", headers=chair_headers).json()[0]

    assert entry["submissionDate"] == ""


def test_an_empty_committee_returns_an_empty_roster(client, chair_headers):
    assert client.get("/api/chair/delegates", headers=chair_headers).json() == []


def test_a_chair_without_a_profile_cannot_list_delegates(client, factory):
    account = factory.account(role="chair", identifier="CHAIR-NO-ROSTER")

    response = client.get("/api/chair/delegates", headers=factory.headers(account))

    assert response.status_code == 404
    assert response.json() == {"message": "No chair profile is attached to this account."}


# ---------------------------------------------------------------------------
# POST /chair/papers/{id}/grade
# ---------------------------------------------------------------------------


def test_grading_stores_the_marks_and_recomputes_the_total(
    client, factory, db, chair_headers, committee, school
):
    """The stored total comes from the rubric, not from the ``totalScore`` in the body.

    The body claims ``999/999``; the response and the row both say ``17/20``, which is the
    sum of the marks over the sum of the maxima. Comments are trimmed on the way in.
    """
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "scores": {"clarity": 8, "evidence": 4, "style": 5},
            "totalScore": "999/999",
            "comments": "  Good work.  ",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Grade saved.", "totalScore": "17/20"}

    db.expire_all()
    assert delegate.paper_status == "graded"
    assert delegate.paper_grade == "17/20"
    assert delegate.paper_rubric_grade == {"clarity": 8.0, "evidence": 4.0, "style": 5.0}
    assert delegate.paper_comments == "Good work."


def test_a_mark_equal_to_the_maximum_is_accepted(
    client, factory, chair_headers, committee, school
):
    """Full marks must not be lost to floating-point comparison."""
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "scores": {"clarity": 10, "evidence": 5, "style": 5},
            "totalScore": "",
        },
    )

    assert response.status_code == 200
    assert response.json()["totalScore"] == "20/20"


def test_a_mark_above_the_maximum_is_400_and_names_the_criterion(
    client, factory, chair_headers, committee, school
):
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {"clarity": 11}, "totalScore": ""},
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "Clarity must be between 0 and 10; got 11."
    }


def test_a_negative_mark_is_400(client, factory, chair_headers, committee, school):
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {"style": -1}, "totalScore": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Style must be between 0 and 5; got -1."}


def test_a_criterion_that_left_the_rubric_is_400(
    client, factory, chair_headers, committee, school
):
    """A stale tab can still hold the old ids; the server refuses rather than parking them."""
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {"retired": 3}, "totalScore": ""},
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "scores contains criteria that are not in the rubric: retired."
    }


def test_grading_without_a_configured_rubric_is_400(
    client, factory, chair_headers, committee, school
):
    """Nothing can be graded before an admin writes the rubric."""
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {}, "totalScore": ""},
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "The grading rubric has no criteria configured yet."
    }


def test_an_unsubmitted_paper_is_409_when_grading(
    client, factory, chair_headers, committee, school
):
    """409, not 404: the delegate exists, the paper does not - the request conflicts."""
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="unsubmitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {}, "totalScore": ""},
    )

    assert response.status_code == 409
    assert response.json() == {
        "message": "This delegate has not submitted a position paper yet."
    }


def test_a_delegate_from_another_committee_cannot_be_graded(
    client, factory, chair_headers, school
):
    """The scope is the committee, so a foreign delegate is simply not found."""
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    foreign = _delegate_in(factory, _other_committee(factory), school)

    response = client.post(
        f"/api/chair/papers/{foreign.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": foreign.account_id, "scores": {}, "totalScore": ""},
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No such delegate in your committee."}


def test_regrading_overwrites_the_previous_marks(
    client, factory, db, chair_headers, committee, school
):
    """Correcting a mistake is allowed and replaces the marks rather than adding to them."""
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")
    path = f"/api/chair/papers/{delegate.account_id}/grade"

    first = client.post(
        path,
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {"clarity": 4}, "totalScore": ""},
    )
    second = client.post(
        path,
        headers=chair_headers,
        json={"delegateId": delegate.account_id, "scores": {"clarity": 9}, "totalScore": ""},
    )

    assert first.json()["totalScore"] == "4/20"
    assert second.json()["totalScore"] == "9/20"
    db.expire_all()
    assert delegate.paper_rubric_grade == {"clarity": 9.0}


def test_the_path_id_wins_over_the_body_delegate_id(
    client, factory, db, chair_headers, committee, school
):
    """The body carries a ``delegateId`` for the frontend's convenience; it is not trusted.

    Grading is addressed by the path, so a mismatched body must apply to the path's delegate
    and leave the other one untouched.
    """
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    target = _delegate_in(factory, committee, school, country="France", paper_status="submitted")
    other = _delegate_in(factory, committee, school, country="Spain", paper_status="submitted")

    client.post(
        f"/api/chair/papers/{target.account_id}/grade",
        headers=chair_headers,
        json={"delegateId": other.account_id, "scores": {"clarity": 7}, "totalScore": ""},
    )

    db.expire_all()
    assert target.paper_status == "graded"
    assert other.paper_status == "submitted"


def test_comments_over_the_column_limit_are_rejected_by_validation(
    client, factory, chair_headers, committee, school
):
    """The request model caps the length first, so the domain's own check never fires here.

    The message still has to be the friendly sentence, because it goes into a toast.
    """
    _save_rubric(factory, "paper", PAPER_RUBRIC)
    delegate = _delegate_in(factory, committee, school, paper_status="submitted")

    response = client.post(
        f"/api/chair/papers/{delegate.account_id}/grade",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "scores": {"clarity": 5},
            "totalScore": "",
            "comments": "x" * 501,
        },
    )

    assert response.status_code == 422
    assert response.json() == {"message": "Comments must be at most 500 characters."}


# ---------------------------------------------------------------------------
# GET /chair/papers/{id}/download
# ---------------------------------------------------------------------------


def test_downloads_the_paper_as_a_pdf_named_after_the_country(
    client, factory, chair_headers, committee, school
):
    delegate = _delegate_in(factory, committee, school, country="France")
    factory.upload(delegate, file_path="live.pdf", write_bytes=b"%PDF-live")

    response = client.get(
        f"/api/chair/papers/{delegate.account_id}/download", headers=chair_headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-live"
    assert "France_Position_Paper.pdf" in response.headers["content-disposition"]


def test_the_newest_upload_is_the_one_served(
    client, factory, chair_headers, committee, school
):
    delegate = _delegate_in(factory, committee, school)
    factory.upload(
        delegate, when=datetime(2026, 10, 1), file_path="old.pdf", write_bytes=b"%PDF-old"
    )
    factory.upload(
        delegate, when=datetime(2026, 10, 2), file_path="new.pdf", write_bytes=b"%PDF-new"
    )

    response = client.get(
        f"/api/chair/papers/{delegate.account_id}/download", headers=chair_headers
    )

    assert response.content == b"%PDF-new"


def test_an_unsubmitted_paper_is_404_when_downloading(
    client, factory, chair_headers, committee, school
):
    """The same domain condition as the 409 above, specialised for a fetch."""
    delegate = _delegate_in(factory, committee, school)

    response = client.get(
        f"/api/chair/papers/{delegate.account_id}/download", headers=chair_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No position paper has been submitted yet."}


def test_a_delegate_from_another_committee_cannot_be_downloaded(
    client, factory, chair_headers, school
):
    foreign = _delegate_in(factory, _other_committee(factory), school)
    factory.upload(foreign, file_path="foreign.pdf", write_bytes=b"%PDF-foreign")

    response = client.get(
        f"/api/chair/papers/{foreign.account_id}/download", headers=chair_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No such delegate in your committee."}


def test_a_row_whose_file_is_gone_is_404(
    client, factory, chair_headers, committee, school, papers_dir
):
    delegate = _delegate_in(factory, committee, school)
    factory.upload(delegate, file_path="gone.pdf", write_bytes=b"%PDF-gone")
    (papers_dir / "gone.pdf").unlink()

    response = client.get(
        f"/api/chair/papers/{delegate.account_id}/download", headers=chair_headers
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "The stored file is missing. The paper has to be uploaded again."
    }


# ---------------------------------------------------------------------------
# GET /chair/awards/options
# ---------------------------------------------------------------------------


def test_award_options_are_the_assignable_names(client, chair_headers):
    """The template's own "None" and "Candidate" must not appear, or the list doubles."""
    body = client.get("/api/chair/awards/options", headers=chair_headers).json()

    assert body == [
        "Verbal Commendation",
        "Honorable Mention",
        "Outstanding Delegate",
        "Best Delegate",
    ]
    assert "None" not in body
    assert "Candidate" not in body


def test_reserved_names_and_blank_options_are_filtered(
    client, chair_headers, monkeypatch
):
    """The filter is defensive: a bad entry in core.controls must not reach the dropdown."""
    monkeypatch.setattr(
        controls,
        "award_options",
        ["None", "candidate", "   ", " Best Delegate "],
    )

    assert client.get("/api/chair/awards/options", headers=chair_headers).json() == [
        "Best Delegate"
    ]


# ---------------------------------------------------------------------------
# GET /chair/awards/rubric
# ---------------------------------------------------------------------------


def test_the_awards_rubric_is_empty_until_saved(client, chair_headers):
    assert client.get("/api/chair/awards/rubric", headers=chair_headers).json() == []


def test_a_stored_awards_rubric_keeps_its_levels_and_their_order(
    client, factory, chair_headers
):
    """Levels are rendered as score cells in the order they were saved."""
    _save_rubric(factory, "awards", AWARDS_RUBRIC)

    body = client.get("/api/chair/awards/rubric", headers=chair_headers).json()

    assert body[0] == {
        "id": "speaking",
        "label": "Speaking",
        "levels": [
            {"score": 4.0, "label": "Excellent", "description": "Commanding"},
            {"score": 2.0, "label": "Developing", "description": ""},
        ],
    }


def test_a_criterion_without_levels_is_skipped(client, factory, chair_headers):
    """The view derives each maximum with Math.max(...levels), which is -Infinity if empty."""
    _save_rubric(
        factory,
        "awards",
        [
            {"id": "empty", "label": "Empty", "levels": []},
            {"id": "kept", "label": "Kept", "levels": [{"score": 1, "label": "Only"}]},
        ],
    )

    body = client.get("/api/chair/awards/rubric", headers=chair_headers).json()

    assert [criterion["id"] for criterion in body] == ["kept"]


def test_a_level_without_a_label_is_skipped(client, factory, chair_headers):
    """There would be nothing to render on the score cell."""
    _save_rubric(
        factory,
        "awards",
        [
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": [{"score": 4, "label": "  "}, {"score": 2, "label": "Fine"}],
            }
        ],
    )

    body = client.get("/api/chair/awards/rubric", headers=chair_headers).json()

    assert [level["label"] for level in body[0]["levels"]] == ["Fine"]


# ---------------------------------------------------------------------------
# GET /chair/awards/delegates
# ---------------------------------------------------------------------------


def test_the_award_roster_defaults_to_none_and_a_hidden_total(
    client, factory, chair_headers, committee, school
):
    """A delegate nobody has scored has ``totalScore: null``, so the view hides the badge."""
    delegate = _delegate_in(factory, committee, school)

    entry = client.get("/api/chair/awards/delegates", headers=chair_headers).json()[0]

    assert entry == {
        "id": delegate.account_id,
        "country": "France",
        "committee": "DISEC",
        "assignedAward": "None",
        "scores": {},
        "totalScore": None,
    }


def test_the_award_roster_reports_saved_scores_and_total(
    client, factory, chair_headers, committee, school
):
    _delegate_in(
        factory,
        committee,
        school,
        assigned_award="Best Delegate",
        overall_rubric_scores={"speaking": 4, "diplomacy": 3},
        overall_total_score=7,
    )

    entry = client.get("/api/chair/awards/delegates", headers=chair_headers).json()[0]

    assert entry["assignedAward"] == "Best Delegate"
    assert entry["scores"] == {"speaking": 4.0, "diplomacy": 3.0}
    assert entry["totalScore"] == 7.0


def test_the_award_roster_is_scoped_to_the_committee(
    client, factory, chair_headers, committee, school
):
    for country in ("Spain", "Argentina"):
        _delegate_in(factory, committee, school, country=country)
    _delegate_in(factory, _other_committee(factory), school, country="France")

    body = client.get("/api/chair/awards/delegates", headers=chair_headers).json()

    assert [entry["country"] for entry in body] == ["Argentina", "Spain"]


# ---------------------------------------------------------------------------
# POST /chair/awards/{id}
# ---------------------------------------------------------------------------


def test_an_official_award_requires_every_criterion_and_recomputes_the_total(
    client, factory, db, chair_headers, committee, school
):
    """The body's ``totalScore`` is ignored; the total is the sum of the marks."""
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    delegate = _delegate_in(factory, committee, school)

    response = client.post(
        f"/api/chair/awards/{delegate.account_id}",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "assignedAward": "Best Delegate",
            "scores": {"speaking": 4, "diplomacy": 3},
            "totalScore": 999,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Award saved.", "assignedAward": "Best Delegate"}

    db.expire_all()
    assert delegate.assigned_award == "Best Delegate"
    assert delegate.overall_total_score == 7.0
    assert delegate.overall_rubric_scores == {"speaking": 4.0, "diplomacy": 3.0}


def test_none_and_candidate_need_no_scores(client, factory, db, chair_headers, committee, school):
    """"No award" and "shortlist" are legitimate states, not ungraded awards.

    The total stays NULL rather than 0.0, so the view keeps the badge hidden.
    """
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    delegate = _delegate_in(factory, committee, school)

    response = client.post(
        f"/api/chair/awards/{delegate.account_id}",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "assignedAward": "Candidate",
            "scores": {},
            "totalScore": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["assignedAward"] == "Candidate"

    db.expire_all()
    assert delegate.overall_total_score is None


def test_an_unscored_official_award_is_400_and_lists_what_is_missing(
    client, factory, chair_headers, committee, school
):
    """The frontend greys the button out; the server enforces it because a script would not."""
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    delegate = _delegate_in(factory, committee, school)

    response = client.post(
        f"/api/chair/awards/{delegate.account_id}",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "assignedAward": "Best Delegate",
            "scores": {"speaking": 4},
            "totalScore": 4,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "Every rubric criterion must be scored before assigning Best Delegate. "
        "Missing: Diplomacy."
    }


def test_an_unknown_award_name_is_400_and_lists_the_allowed_ones(
    client, factory, chair_headers, committee, school
):
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    delegate = _delegate_in(factory, committee, school)

    response = client.post(
        f"/api/chair/awards/{delegate.account_id}",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "assignedAward": "Participation Trophy",
            "scores": {},
            "totalScore": 0,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "assignedAward must be one of: Best Delegate, Candidate, "
        "Honorable Mention, None, Outstanding Delegate, Verbal Commendation."
    }


def test_an_unknown_criterion_in_the_award_scores_is_400(
    client, factory, chair_headers, committee, school
):
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    delegate = _delegate_in(factory, committee, school)

    response = client.post(
        f"/api/chair/awards/{delegate.account_id}",
        headers=chair_headers,
        json={
            "delegateId": delegate.account_id,
            "assignedAward": "Best Delegate",
            "scores": {"retired": 3, "speaking": 4, "diplomacy": 3},
            "totalScore": 10,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "scores contains criteria that are not in the rubric: retired."
    }


def test_a_delegate_from_another_committee_cannot_be_awarded(
    client, factory, chair_headers, school
):
    _save_rubric(factory, "awards", AWARDS_RUBRIC)
    foreign = _delegate_in(factory, _other_committee(factory), school)

    response = client.post(
        f"/api/chair/awards/{foreign.account_id}",
        headers=chair_headers,
        json={
            "delegateId": foreign.account_id,
            "assignedAward": "Candidate",
            "scores": {},
            "totalScore": 0,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No such delegate in your committee."}
