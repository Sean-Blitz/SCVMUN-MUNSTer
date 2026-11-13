"""API tests for PUT /admin/rubrics (§8.11): the conference-wide grading rubrics.

Both rubrics are whole documents: what is sent replaces what is stored. There is no merge and
no id matching, and the two keys are independent - the paper editor saving cannot clobber the
awards rubric, and `[]` explicitly empties one while an omitted key leaves it alone.

The one refusal worth understanding: every recorded mark is filed under a criterion ``id``, so
dropping or renaming a criterion that is already graded would silently strand real work (the
delegate's breakdown would lose that line). That is a **409 listing the affected ids**, and
``?force=true`` is the admin's explicit override.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_rubrics.py -v
"""

import pytest

PAPER = [{"id": "clarity", "label": "Clarity", "maxScore": 10}]
AWARDS = [
    {"id": "speaking", "label": "Speaking", "levels": [{"score": 4, "label": "Excellent"}]}
]


def _put(client, headers, *, force=False, **body):
    return client.put(
        "/api/admin/rubrics",
        json=body,
        headers=headers,
        params={"force": str(force).lower()},
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_the_route_refuses_an_anonymous_caller(client):
    response = client.put("/api/admin/rubrics", json={"paper": PAPER})

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


def test_the_route_is_admin_only(client, delegate_headers):
    response = client.put("/api/admin/rubrics", json={"paper": PAPER}, headers=delegate_headers)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# Replacing one or both documents
# ---------------------------------------------------------------------------


def test_the_paper_rubric_can_be_saved_alone(client, admin_headers):
    """Omitting ``awards`` leaves that document untouched, so the two editors cannot collide."""
    response = _put(client, admin_headers, paper=PAPER)

    assert response.status_code == 200
    body = response.json()
    assert body["paper"] == [{"id": "clarity", "label": "Clarity", "maxScore": 10.0}]
    assert body["awards"] == []


def test_the_saved_rubric_is_what_the_graders_read(client, admin_headers):
    """The response is a re-read, and GET /chair/rubric is open to admins for exactly this."""
    _put(client, admin_headers, paper=PAPER)

    assert client.get("/api/chair/rubric", headers=admin_headers).json() == [
        {"id": "clarity", "label": "Clarity", "maxScore": 10.0}
    ]


def test_the_awards_rubric_can_be_saved_alone(client, admin_headers):
    response = _put(client, admin_headers, awards=AWARDS)

    assert response.status_code == 200
    body = response.json()
    assert body["paper"] == []  # untouched, and never saved
    assert body["awards"][0]["levels"] == [
        {"score": 4.0, "label": "Excellent", "description": ""}
    ]


def test_saving_the_awards_rubric_leaves_the_paper_one_alone(client, admin_headers):
    _put(client, admin_headers, paper=PAPER)

    response = _put(client, admin_headers, awards=AWARDS)

    assert response.json()["paper"] == [{"id": "clarity", "label": "Clarity", "maxScore": 10.0}]


def test_sending_neither_rubric_is_400(client, admin_headers):
    response = client.put("/api/admin/rubrics", json={}, headers=admin_headers)

    assert response.status_code == 400
    assert response.json() == {
        "message": "Send the paper rubric, the awards rubric, or both."
    }


def test_an_empty_array_clears_a_rubric(client, admin_headers):
    """`[]` is an answer ("no criteria"); omitting the key is not."""
    _put(client, admin_headers, paper=PAPER)

    response = _put(client, admin_headers, paper=[])

    assert response.status_code == 200
    assert response.json()["paper"] == []


# ---------------------------------------------------------------------------
# Refusals from the domain
# ---------------------------------------------------------------------------


def test_a_repeated_criterion_id_is_400(client, admin_headers):
    """Every mark is filed under the id, so a duplicate would make it ambiguous."""
    response = _put(
        client,
        admin_headers,
        paper=[
            {"id": "clarity", "label": "Clarity", "maxScore": 10},
            {"id": "clarity", "label": "Also clarity", "maxScore": 5},
        ],
    )

    assert response.status_code == 400
    assert "more than once" in response.json()["message"]


def test_a_blank_label_is_400(client, admin_headers):
    response = _put(client, admin_headers, paper=[{"id": "clarity", "label": "  ", "maxScore": 10}])

    assert response.status_code == 400
    assert "needs a label" in response.json()["message"]


def test_a_blank_level_label_is_400(client, admin_headers):
    response = _put(
        client,
        admin_headers,
        awards=[
            {
                "id": "speaking",
                "label": "Speaking",
                "levels": [{"score": 4, "label": "  "}],
            }
        ],
    )

    assert response.status_code == 400
    assert "needs a label" in response.json()["message"]


def test_a_dropped_criterion_with_recorded_marks_is_409(
    client, factory, admin_headers, committee, school
):
    """The refusal exists so a save cannot silently delete someone's grade line."""
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6}, paper_status="graded")

    response = _put(
        client, admin_headers, paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}]
    )

    assert response.status_code == 409
    assert "clarity" in response.json()["message"]


def test_force_saves_over_recorded_marks(client, factory, admin_headers, committee, school):
    """The override is explicit: the marks stay in the database but leave the breakdown."""
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6}, paper_status="graded")

    response = _put(
        client,
        admin_headers,
        force=True,
        paper=[{"id": "evidence", "label": "Evidence", "maxScore": 5}],
    )

    assert response.status_code == 200
    assert [criterion["id"] for criterion in response.json()["paper"]] == ["evidence"]


def test_keeping_the_marked_criterion_is_fine(client, factory, admin_headers, committee, school):
    """The check is about dropped ids, not about editing a rubric that has been used."""
    factory.new_delegate(committee, school, paper_rubric_grade={"clarity": 6}, paper_status="graded")

    response = _put(
        client, admin_headers, paper=[{"id": "clarity", "label": "Clarity", "maxScore": 20}]
    )

    assert response.status_code == 200
    assert response.json()["paper"][0]["maxScore"] == 20.0
