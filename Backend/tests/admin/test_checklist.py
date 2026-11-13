"""API tests for the conference checklist (§8.7): shared labels, per-school ticks.

The label list is conference-wide; a tick is per school. That split is why the labels are
**reconciled by id** rather than replaced wholesale: a line's id is what every school's
progress row points at, so updating a line in place is what lets a rename keep its ticks.
A line that is absent from the PUT is deleted, taking its progress with it - which is the
admin's explicit way to remove one.

The tick routes accept a line by ``id`` or by ``label`` (so a script can address one from the
labels it just read), require exactly one of the two, and do not touch lines they were not
given.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_checklist.py -v
"""

import pytest

from crud.database_schema import ChecklistProgress, ConferenceChecklist

CHECKLIST_ROUTES = [
    ("get", "/api/admin/checklist", {}),
    ("put", "/api/admin/checklist", {"json": {"items": []}}),
    ("get", "/api/admin/schools/1/checklist", {}),
    ("patch", "/api/admin/schools/1/checklist", {"json": {"items": []}}),
]


def _set_labels(client, headers, *labels):
    return client.put(
        "/api/admin/checklist",
        json={"items": [{"label": label} for label in labels]},
        headers=headers,
    )


def _ticks(client, headers, school, items):
    return client.patch(
        f"/api/admin/schools/{school.account_id}/checklist",
        json={"items": items},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", CHECKLIST_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", CHECKLIST_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# GET / PUT /admin/checklist
# ---------------------------------------------------------------------------


def test_the_checklist_starts_empty(client, admin_headers):
    assert client.get("/api/admin/checklist", headers=admin_headers).json() == {"items": []}


def test_putting_labels_assigns_ids_in_order(client, admin_headers):
    response = _set_labels(client, admin_headers, "Submit position papers", "Pay the fee")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["label"] for item in items] == ["Submit position papers", "Pay the fee"]
    assert all(item["id"] > 0 for item in items)


def test_a_line_keeps_its_id_when_its_label_changes(client, db, admin_headers):
    """The id is what every school's tick points at, so it must survive an edit."""
    first = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]
    line_id = first["id"]

    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"id": line_id, "label": "Pay the conference fee"}]},
        headers=admin_headers,
    )

    items = response.json()["items"]
    assert [item["id"] for item in items] == [line_id]
    assert items[0]["label"] == "Pay the conference fee"
    assert db.get(ConferenceChecklist, line_id).label == "Pay the conference fee"


def test_a_tick_survives_a_label_rename(client, factory, db, admin_headers, school):
    """Renaming edits the shared line; the school's tick is untouched."""
    line = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]
    _ticks(client, admin_headers, school, [{"id": line["id"], "completed": True}])

    client.put(
        "/api/admin/checklist",
        json={"items": [{"id": line["id"], "label": "Pay the conference fee"}]},
        headers=admin_headers,
    )

    progress = db.get(ChecklistProgress, (school.account_id, line["id"]))
    assert progress.completed is True


def test_a_line_that_is_absent_is_deleted_with_its_ticks(
    client, factory, db, admin_headers, school
):
    """Removing a line from the PUT is how the admin deletes it, ticks included."""
    items = _set_labels(client, admin_headers, "Pay the fee", "Book travel").json()["items"]
    _ticks(client, admin_headers, school, [{"id": items[0]["id"], "completed": True}])
    kept = items[1]

    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"id": kept["id"], "label": kept["label"]}]},
        headers=admin_headers,
    )

    assert [item["label"] for item in response.json()["items"]] == ["Book travel"]
    assert db.get(ConferenceChecklist, items[0]["id"]) is None
    assert db.get(ChecklistProgress, (school.account_id, items[0]["id"])) is None


def test_a_blank_label_is_400_and_names_the_position(client, admin_headers):
    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"label": "Fine"}, {"label": "   "}]},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Item 2 needs a label."}


def test_a_repeated_label_is_400_and_names_the_offender(client, admin_headers):
    """Labels are unique case-insensitively, so a script can address a line by name."""
    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"label": "Pay the fee"}, {"label": "pay the FEE"}]},
        headers=admin_headers,
    )

    # The position and the label are the *second* line's, as typed.
    assert response.status_code == 400
    assert response.json() == {"message": "Item 2 repeats the label 'pay the FEE'."}


def test_an_over_long_label_is_rejected_by_validation(client, admin_headers):
    """The request model caps the length first, so the domain's own check never fires here.

    The message still has to be the friendly sentence, because it goes into a toast.
    """
    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"label": "x" * 201}]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "message": "Label (entry 1) must be at most 200 characters."
    }


def test_the_checklist_has_a_cap(client, admin_headers):
    response = client.put(
        "/api/admin/checklist",
        json={"items": [{"label": f"Line {n}"} for n in range(21)]},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json() == {"message": "A checklist holds at most 20 items."}


# ---------------------------------------------------------------------------
# GET /admin/schools/{id}/checklist
# ---------------------------------------------------------------------------


def test_a_school_checklist_joins_the_labels_with_its_ticks(
    client, admin_headers, school
):
    _set_labels(client, admin_headers, "Pay the fee", "Book travel")

    body = client.get(
        f"/api/admin/schools/{school.account_id}/checklist", headers=admin_headers
    ).json()

    assert body["school_id"] == school.account_id
    assert body["school_name"] == "Test High School"
    assert [(item["label"], item["completed"]) for item in body["items"]] == [
        ("Pay the fee", False),
        ("Book travel", False),
    ]


def test_an_unknown_school_is_404(client, admin_headers):
    response = client.get("/api/admin/schools/999999/checklist", headers=admin_headers)

    assert response.status_code == 404
    assert response.json() == {"message": "No school with id 999999."}


# ---------------------------------------------------------------------------
# PATCH /admin/schools/{id}/checklist
# ---------------------------------------------------------------------------


def test_a_line_can_be_ticked_by_id(client, admin_headers, school):
    line = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]

    response = _ticks(client, admin_headers, school, [{"id": line["id"], "completed": True}])

    assert response.status_code == 200
    assert response.json()["items"][0]["completed"] is True


def test_a_line_can_be_ticked_by_label(client, admin_headers, school):
    """A script reads the labels, then addresses one without knowing its id."""
    _set_labels(client, admin_headers, "Pay the fee")

    response = _ticks(
        client, admin_headers, school, [{"label": "Pay the fee", "completed": True}]
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["completed"] is True


def test_an_untouched_line_keeps_its_state(client, admin_headers, school):
    """The update is partial: lines not listed keep whatever they already had."""
    items = _set_labels(client, admin_headers, "Pay the fee", "Book travel").json()["items"]
    _ticks(client, admin_headers, school, [{"id": items[0]["id"], "completed": True}])

    response = _ticks(
        client, admin_headers, school, [{"id": items[1]["id"], "completed": True}]
    )

    assert [entry["completed"] for entry in response.json()["items"]] == [True, True]


def test_addressing_a_line_both_ways_is_400(client, admin_headers, school):
    line = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]

    response = _ticks(
        client,
        admin_headers,
        school,
        [{"id": line["id"], "label": "Pay the fee", "completed": True}],
    )

    assert response.status_code == 400
    assert response.json() == {
        "message": "Item 1 must give exactly one of id or label."
    }


def test_addressing_a_line_neither_way_is_400(client, admin_headers, school):
    _set_labels(client, admin_headers, "Pay the fee")

    response = _ticks(client, admin_headers, school, [{"completed": True}])

    assert response.status_code == 400
    assert response.json() == {
        "message": "Item 1 must give exactly one of id or label."
    }


def test_an_unknown_line_id_is_404(client, admin_headers, school):
    response = _ticks(client, admin_headers, school, [{"id": 999999, "completed": True}])

    assert response.status_code == 404
    assert response.json() == {"message": "No checklist item with id 999999."}


def test_an_unknown_label_is_404(client, admin_headers, school):
    _set_labels(client, admin_headers, "Pay the fee")

    response = _ticks(
        client, admin_headers, school, [{"label": "No such line", "completed": True}]
    )

    assert response.status_code == 404
    assert response.json() == {
        "message": "No checklist item labelled 'No such line'."
    }


def test_ticking_for_an_unknown_school_is_404(client, admin_headers):
    line = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]

    response = client.patch(
        "/api/admin/schools/999999/checklist",
        json={"items": [{"id": line["id"], "completed": True}]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"message": "No school with id 999999."}


def test_one_schools_tick_is_invisible_to_another(
    client, factory, admin_headers, school
):
    """The labels are shared; the ticks are not."""
    rival = factory.account(role="advisor", name="Rival Advisor")
    rival_school = factory.school(rival, name="Rival High")
    line = _set_labels(client, admin_headers, "Pay the fee").json()["items"][0]

    _ticks(client, admin_headers, school, [{"id": line["id"], "completed": True}])

    rival_checklist = client.get(
        f"/api/admin/schools/{rival_school.account_id}/checklist", headers=admin_headers
    ).json()

    assert rival_checklist["items"][0]["completed"] is False
