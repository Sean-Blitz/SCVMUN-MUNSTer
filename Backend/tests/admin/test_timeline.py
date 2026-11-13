"""API tests for the conference timeline (§8.8).

The schedule is one list of points in time shared by every committee. The editor replaces it
wholesale - the payload carries no ids, because an event has no identity worth preserving - so
the server sorts by time and returns what it stored.

The one row with an identity is the pinned "Conference Start": its ``starts_at`` is the
conference's start and the target of the header countdown. It can be **re-dated** but not
removed or renamed, and because the payload has no ids the match is by ``(phase, label)`` -
which is why the label is part of the rule.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_timeline.py -v
"""

from datetime import datetime

import pytest

from crud.database_schema import TimelineEvent

TIMELINE_ROUTES = [
    ("get", "/api/admin/timeline", {}),
    ("put", "/api/admin/timeline", {"json": {"events": []}}),
]


def _event(label="Position papers due", phase="preConference", starts_at="2026-12-01T09:00:00"):
    return {"phase": phase, "label": label, "starts_at": starts_at}


def _replace(client, headers, *events):
    return client.put(
        "/api/admin/timeline", json={"events": list(events)}, headers=headers
    )


def _pin_conference_start(factory, *, starts_at=datetime(2027, 1, 30)):
    factory.db.add(
        TimelineEvent(
            phase="preConference",
            label="Conference Start",
            starts_at=starts_at,
            pinned=True,
        )
    )
    factory.db.commit()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", TIMELINE_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", TIMELINE_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# GET / PUT /admin/timeline
# ---------------------------------------------------------------------------


def test_the_timeline_starts_empty(client, admin_headers):
    assert client.get("/api/admin/timeline", headers=admin_headers).json() == {"events": []}


def test_events_come_back_sorted_by_time(client, admin_headers):
    """The payload is sent in any order; the view relies on ascending time."""
    response = _replace(
        client,
        admin_headers,
        _event("Second", starts_at="2027-01-01T09:00:00"),
        _event("Conference", phase="duringConference", starts_at="2027-02-01T09:00:00"),
        _event("First", starts_at="2026-12-01T09:00:00"),
    )

    assert response.status_code == 200
    events = response.json()["events"]
    assert [event["label"] for event in events] == ["First", "Second", "Conference"]
    assert [event["pinned"] for event in events] == [False, False, False]


def test_the_payload_replaces_the_whole_schedule(client, admin_headers):
    """Nothing else references an event, so it is a delete-then-insert."""
    _replace(client, admin_headers, _event("Old one"), _event("Old two"))

    response = _replace(client, admin_headers, _event("Only this one"))

    assert [event["label"] for event in response.json()["events"]] == ["Only this one"]


def test_the_conference_start_can_be_re_dated(client, factory, admin_headers):
    """Re-dating is the one edit the pinned row allows - it is how the countdown is set."""
    _pin_conference_start(factory)
    pinned = client.get("/api/admin/timeline", headers=admin_headers).json()["events"][0]
    assert pinned["pinned"] is True

    response = replace = _replace(
        client,
        admin_headers,
        _event("Conference Start", starts_at="2027-02-15T10:00:00"),
    )

    assert response.status_code == 200
    events = replace.json()["events"]
    assert len(events) == 1
    assert events[0]["pinned"] is True
    assert events[0]["starts_at"].startswith("2027-02-15T10:00:00")


def test_removing_the_conference_start_is_400(client, factory, admin_headers):
    """A schedule without it would take the conference's start time - and the countdown."""
    _pin_conference_start(factory)

    response = _replace(client, admin_headers, _event("Something else"))

    assert response.status_code == 400
    assert response.json() == {
        "message": "'Conference Start' is the conference's start and cannot be removed or "
        "renamed. Change its time instead."
    }


def test_renaming_the_conference_start_is_400(client, factory, admin_headers):
    """The match is by (phase, label), so a rename looks exactly like a removal."""
    _pin_conference_start(factory)

    response = _replace(client, admin_headers, _event("Opening Ceremony"))

    assert response.status_code == 400
    assert "cannot be removed or renamed" in response.json()["message"]


def test_an_invalid_phase_is_400(client, admin_headers):
    response = _replace(client, admin_headers, _event(phase="intermission"))

    assert response.status_code == 400
    assert response.json() == {
        "message": "Event 1: phase must be one of preConference, duringConference."
    }


def test_an_aware_timestamp_is_400(client, admin_headers):
    """The column is naive UTC; an aware value would land shifted by the session's offset."""
    response = _replace(client, admin_headers, _event(starts_at="2027-01-01T00:00:00+00:00"))

    assert response.status_code == 400
    assert response.json() == {
        "message": "Event 1: send starts_at as naive UTC, with no timezone suffix."
    }


def test_a_blank_label_is_400(client, admin_headers):
    response = _replace(client, admin_headers, _event(label="   "))

    assert response.status_code == 400
    assert response.json() == {"message": "Event 1 needs a label."}


def test_an_over_long_label_is_rejected_by_validation(client, admin_headers):
    """The request model caps the length first, so the domain's own check never fires here."""
    response = _replace(client, admin_headers, _event(label="x" * 201))

    assert response.status_code == 422
    assert response.json() == {
        "message": "Label (entry 1) must be at most 200 characters."
    }


def test_the_timeline_has_a_cap(client, admin_headers):
    events = [_event(f"Event {n}") for n in range(31)]

    response = _replace(client, admin_headers, *events)

    assert response.status_code == 400
    assert response.json() == {"message": "The timeline holds at most 30 events."}
