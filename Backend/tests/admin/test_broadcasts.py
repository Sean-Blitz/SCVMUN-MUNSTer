"""API tests for the broadcast routes (§8.6): the announcements and conference links.

The delegate dashboard has room for 2 global + 1 committee announcement and 2 global + 3
committee links. The caps are enforced here rather than by the schema, because they count only
the rows a delegate can still *see*: a line with no end date, or one ending in the future, holds
a slot; an expired one frees it. That rule is why a create or edit with a past ``ends_at`` skips
the check entirely, and why deleting frees a slot immediately.

Two smaller contracts are pinned too: ``kind`` is fixed at creation (changing a line between
the announcement bar and the link strip means delete + create), and a link must have a url
while an announcement must not.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_broadcasts.py -v
"""

import pytest

import core.audit

BROADCAST_ROUTES = [
    ("get", "/api/admin/broadcasts", {}),
    ("post", "/api/admin/broadcasts", {"json": {"kind": "announcement", "body": "x"}}),
    ("patch", "/api/admin/broadcasts/1", {"json": {"body": "x"}}),
    ("delete", "/api/admin/broadcasts/1", {}),
]


def _announcement(client, headers, body="Notice", **extra):
    return client.post(
        "/api/admin/broadcasts", json={"kind": "announcement", "body": body, **extra},
        headers=headers,
    )


def _link(client, headers, body="Handbook", url="https://example.test/hb", **extra):
    return client.post(
        "/api/admin/broadcasts",
        json={"kind": "link", "body": body, "url": url, **extra},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", BROADCAST_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", BROADCAST_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# POST /admin/broadcasts
# ---------------------------------------------------------------------------


def test_an_announcement_is_published(client, admin_headers):
    response = _announcement(client, admin_headers, body="  Lunch at noon.  ")

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "announcement"
    assert body["body"] == "Lunch at noon."  # stripped before storing
    assert body["committee_name"] is None  # addressed to every delegate
    assert body["url"] is None
    assert body["position"] == 0
    assert body["id"] > 0
    assert body["created_at"]


def test_a_link_is_published_with_its_url(client, admin_headers):
    response = _link(client, admin_headers)

    assert response.status_code == 201
    assert response.json()["url"] == "https://example.test/hb"


def test_a_link_without_a_url_is_400(client, admin_headers):
    response = client.post(
        "/api/admin/broadcasts",
        json={"kind": "link", "body": "Handbook"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "A conference link needs a url."}


def test_an_announcement_cannot_carry_a_url(client, admin_headers):
    response = _announcement(client, admin_headers, url="https://example.test")

    assert response.status_code == 400
    assert response.json() == {"message": "An announcement cannot carry a url."}


def test_an_unknown_kind_is_400_and_lists_the_choices(client, admin_headers):
    response = client.post(
        "/api/admin/broadcasts",
        json={"kind": "headline", "body": "x"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "kind must be one of: announcement, link."}


def test_an_empty_body_is_400(client, admin_headers):
    response = _announcement(client, admin_headers, body="   ")

    assert response.status_code == 400
    assert response.json() == {"message": "body cannot be empty."}


def test_an_unknown_committee_is_404(client, admin_headers):
    """The committee list is authoritative, so a typo cannot create a phantom target."""
    response = _announcement(client, admin_headers, committee_name="NONEXISTENT")

    assert response.status_code == 404
    assert response.json() == {"message": "Unknown committee 'NONEXISTENT'."}


def test_an_inverted_window_is_400(client, admin_headers):
    """Rejected here rather than by the schema's CHECK constraint, so the message is a sentence."""
    response = _announcement(
        client,
        admin_headers,
        starts_at="2027-01-02T00:00:00",
        ends_at="2027-01-01T00:00:00",
    )

    assert response.status_code == 400
    assert response.json() == {"message": "ends_at must be after starts_at."}


def test_the_global_announcement_cap_is_two(client, admin_headers):
    assert _announcement(client, admin_headers, body="One").status_code == 201
    assert _announcement(client, admin_headers, body="Two").status_code == 201

    third = _announcement(client, admin_headers, body="Three")

    assert third.status_code == 409
    assert third.json() == {
        "message": "At most 2 live announcements are allowed for every delegate. "
        "Delete one first."
    }


def test_an_expired_line_does_not_hold_a_slot(client, admin_headers):
    """The cap bounds what a delegate can see, so two expired lines free both slots."""
    for body in ("Old one", "Old two"):
        assert _announcement(
            client,
            admin_headers,
            body=body,
            starts_at="2026-01-01T00:00:00",
            ends_at="2026-01-02T00:00:00",
        ).status_code == 201

    assert _announcement(client, admin_headers, body="Live one").status_code == 201
    assert _announcement(client, admin_headers, body="Live two").status_code == 201


def test_the_committee_announcement_cap_is_one(client, admin_headers, committee):
    assert _announcement(client, admin_headers, committee_name="DISEC").status_code == 201

    second = _announcement(client, admin_headers, body="Another", committee_name="DISEC")

    assert second.status_code == 409
    assert second.json() == {
        "message": "At most 1 live announcements are allowed for DISEC. Delete one first."
    }


def test_publishing_is_audited(client, admin_headers):
    before = core.audit.read("business")

    _announcement(client, admin_headers, body="Audited line")

    written = core.audit.read("business")[len(before):]
    assert "broadcast.published" in written
    assert "target=all" in written


# ---------------------------------------------------------------------------
# GET /admin/broadcasts
# ---------------------------------------------------------------------------


def test_the_editor_list_shows_expired_lines_too(client, admin_headers):
    """This is the editor's view, not the delegate's: an expired line must be deletable."""
    _announcement(
        client,
        admin_headers,
        body="Expired",
        starts_at="2026-01-01T00:00:00",
        ends_at="2026-01-02T00:00:00",
    )

    body = client.get("/api/admin/broadcasts", headers=admin_headers).json()

    assert [entry["body"] for entry in body["broadcasts"]] == ["Expired"]


def test_the_list_can_be_filtered_by_kind(client, admin_headers):
    _announcement(client, admin_headers, body="Notice")
    _link(client, admin_headers, body="Handbook")

    body = client.get(
        "/api/admin/broadcasts", params={"kind": "link"}, headers=admin_headers
    ).json()

    assert [entry["kind"] for entry in body["broadcasts"]] == ["link"]


def test_an_unknown_kind_filter_is_400(client, admin_headers):
    response = client.get(
        "/api/admin/broadcasts", params={"kind": "headline"}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json() == {"message": "kind must be one of: announcement, link."}


# ---------------------------------------------------------------------------
# PATCH /admin/broadcasts/{id}
# ---------------------------------------------------------------------------


def test_an_edit_applies_only_what_was_sent(client, admin_headers):
    created = _announcement(client, admin_headers, body="Original", position=1).json()

    response = client.patch(
        f"/api/admin/broadcasts/{created['id']}",
        json={"body": "Corrected"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["body"] == "Corrected"
    assert body["position"] == 1  # untouched
    assert body["updated_at"] is not None


def test_a_null_end_date_clears_the_schedule(client, admin_headers):
    """Omitting ``ends_at`` leaves it alone; sending null removes the planned end."""
    created = _announcement(
        client,
        admin_headers,
        starts_at="2027-01-01T00:00:00",
        ends_at="2027-01-02T00:00:00",
    ).json()

    response = client.patch(
        f"/api/admin/broadcasts/{created['id']}",
        json={"ends_at": None},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["ends_at"] is None
    assert response.json()["starts_at"] is not None


def test_an_edit_that_would_overflow_its_target_is_409(client, admin_headers, committee):
    """Moving a line to a busier committee re-checks the cap against the *new* target."""
    assert _announcement(client, admin_headers, committee_name="DISEC").status_code == 201
    elsewhere = _announcement(client, admin_headers, body="Elsewhere").json()

    response = client.patch(
        f"/api/admin/broadcasts/{elsewhere['id']}",
        json={"committee_name": "DISEC"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert "At most 1 live announcements" in response.json()["message"]


def test_editing_an_unknown_broadcast_is_404(client, admin_headers):
    response = client.patch(
        "/api/admin/broadcasts/999999", json={"body": "x"}, headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No broadcast with id 999999."}


def test_an_empty_edit_is_still_a_valid_no_op(client, admin_headers):
    """An empty patch re-validates and saves the row unchanged rather than erroring."""
    created = _announcement(client, admin_headers, body="Unchanged").json()

    response = client.patch(
        f"/api/admin/broadcasts/{created['id']}", json={}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["body"] == "Unchanged"


# ---------------------------------------------------------------------------
# DELETE /admin/broadcasts/{id}
# ---------------------------------------------------------------------------


def test_deleting_a_broadcast_frees_the_slot(client, admin_headers):
    first = _announcement(client, admin_headers, body="One").json()
    _announcement(client, admin_headers, body="Two")
    assert _announcement(client, admin_headers, body="Three").status_code == 409

    deleted = client.delete(f"/api/admin/broadcasts/{first['id']}", headers=admin_headers)
    assert deleted.status_code == 204

    assert _announcement(client, admin_headers, body="Three").status_code == 201


def test_deleting_an_unknown_broadcast_is_404(client, admin_headers):
    response = client.delete("/api/admin/broadcasts/999999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json() == {"message": "No broadcast with id 999999."}
