"""API tests for the public routes: ``/``, ``/healthz`` and ``GET /api/conference``.

These three are the only routes with no token and no role, and each one has a job beyond
serving a page:

* ``/healthz`` is what the container's ``HEALTHCHECK`` and any external monitor poll, so its
  **503 when the database is unreachable** is the whole point - a process-only check would
  report healthy while every request fails;
* ``/api/conference`` feeds the header countdown. It returns ``starts_at: null`` rather than
  inventing a date, which is what lets the header render nothing instead of ``NaN``;
* both must stay reachable without an ``Authorization`` header, because the login page shows
  the countdown before anyone has a token.

``/`` is not part of the frontend contract, but it is what a human hits first, so its shape is
pinned too.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/meta/test_endpoints.py -v
"""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import core.audit
from crud.database_schema import TimelineEvent
from crud.db import get_db
from main import app


@pytest.fixture()
def database_down():
    """Make every request's ``get_db`` hand back a session whose queries fail.

    Overriding the dependency is the only way to exercise the 503 branch without stopping
    PostgreSQL, which would break every other test in the session. The override is removed
    afterwards even if the test fails.
    """

    class _Unreachable:
        def execute(self, *args, **kwargs):
            raise SQLAlchemyError("connection refused")

        def close(self):
            pass

    app.dependency_overrides[get_db] = _Unreachable
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


def test_the_root_route_points_at_the_docs(client):
    """Not part of the contract, but it is the first URL a human opens."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "SCVMUN Platform API",
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------


def test_healthz_reports_ok_without_a_token(client):
    """The probe must be unauthenticated: a container healthcheck has no credentials."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_is_503_when_the_database_is_unreachable(client, database_down):
    """The failure a process-only check hides.

    The body is the usual ``{"message": ...}`` shape, so a monitor reading the JSON gets a
    sentence rather than a bare status line.
    """
    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"message": "Database unavailable."}


def test_healthz_recovers_when_the_database_comes_back(client, database_down):
    """The override is a per-test resource; the next request uses the real session again."""
    assert client.get("/healthz").status_code == 503

    app.dependency_overrides.pop(get_db, None)

    assert client.get("/healthz").status_code == 200


def test_healthz_leaks_nothing_but_up_or_down(client, database_down):
    """An unauthenticated probe must not become a diagnostic endpoint."""
    body = client.get("/healthz").text

    assert "postgres" not in body.lower()
    assert "SELECT" not in body
    assert "Traceback" not in body


# ---------------------------------------------------------------------------
# GET /api/conference
# ---------------------------------------------------------------------------


def test_conference_start_is_null_when_the_pinned_event_is_missing(client):
    """A database that was never seeded must produce "no date", not an error.

    This is the case that silently removes the header countdown: the endpoint is healthy,
    the payload is simply empty, and the component renders nothing.
    """
    response = client.get("/api/conference")

    assert response.status_code == 200
    assert response.json() == {"label": "Conference Start", "starts_at": None}


def test_conference_start_is_public(client, factory):
    """The header shows the countdown on the login page, before any token exists."""
    factory.db.add(
        TimelineEvent(
            phase="preConference", label="Conference Start", starts_at=datetime(2027, 1, 30), pinned=True
        )
    )
    factory.db.commit()

    response = client.get("/api/conference")

    assert response.status_code == 200
    assert response.json()["starts_at"] == "2027-01-30T00:00:00+00:00"


def test_the_timestamp_carries_an_explicit_utc_offset(client, factory):
    """The column is naive UTC; without the offset a browser reads it as local time.

    That would shift the countdown by the viewer's timezone for some delegates and not
    others - the kind of bug that only appears on the day.
    """
    factory.db.add(
        TimelineEvent(
            phase="preConference",
            label="Conference Start",
            starts_at=datetime(2027, 1, 30, 9, 15),
            pinned=True,
        )
    )
    factory.db.commit()

    starts_at = client.get("/api/conference").json()["starts_at"]

    assert starts_at.endswith("+00:00")
    assert starts_at == "2027-01-30T09:15:00+00:00"


def test_the_label_comes_from_the_event_not_the_code(client, factory):
    """The response echoes the row, so an admin renaming the line changes the header text."""
    factory.db.add(
        TimelineEvent(
            phase="preConference",
            label="SCVMUN XXIV opens",
            starts_at=datetime(2027, 1, 30),
            pinned=True,
        )
    )
    factory.db.commit()

    assert client.get("/api/conference").json()["label"] == "SCVMUN XXIV opens"


def test_only_the_pinned_event_is_used(client, factory):
    """Other timeline events are schedule lines, not the conference's start.

    The first-by-time row is deliberately *not* the pinned one, so an implementation that
    took "the earliest event" would return the wrong date here.
    """
    factory.db.add_all(
        [
            TimelineEvent(
                phase="preConference", label="Position papers due", starts_at=datetime(2026, 12, 1)
            ),
            TimelineEvent(
                phase="preConference", label="Conference Start", starts_at=datetime(2027, 1, 30), pinned=True
            ),
        ]
    )
    factory.db.commit()

    body = client.get("/api/conference").json()

    assert body["label"] == "Conference Start"
    assert body["starts_at"] == "2027-01-30T00:00:00+00:00"


def test_a_pinned_date_in_the_past_is_returned_as_is(client, factory):
    """The endpoint reports the date; "it is live" is the client's judgement.

    Returning null here would make the header hide the timer exactly during the conference,
    when the "Conference is Live!" state is what it should show.
    """
    factory.db.add(
        TimelineEvent(
            phase="duringConference", label="Conference Start", starts_at=datetime(2025, 1, 1), pinned=True
        )
    )
    factory.db.commit()

    assert client.get("/api/conference").json()["starts_at"] == "2025-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# The error shape shared by every route
# ---------------------------------------------------------------------------


def test_an_unknown_route_answers_with_the_message_shape(client):
    """Every error path in the app returns ``{"message": ...}``, never FastAPI's ``detail``.

    The frontend reads ``error.response.data.message`` for its toast, so a route that slipped
    through with the default shape would show nothing at all.
    """
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"message": "Not Found"}


def test_a_public_route_does_not_require_a_token(client):
    """Nothing in this file sends an Authorization header; that is the point of the file."""
    for path in ("/", "/healthz", "/api/conference"):
        assert client.get(path).status_code == 200
