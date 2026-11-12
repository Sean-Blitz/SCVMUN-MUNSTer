"""GET /chair/committee/overview — the chair's own committee panel.

The response is what the Committee Overview page renders: the chair's name, the committee's
identity (name, type, topic) and the counts behind the two progress lines. The counters and
the timeline are covered in ``test_endpoints.py``; these two tests are about the committee row
being joined in at all.

The chair account and its ``chairs`` row come from the ``chair``/``chair_headers`` fixtures in
``tests/chair/conftest.py``, which is also where a chair for a *second* committee comes from
(``make_chair``).
"""


def test_overview_carries_the_committees_type_and_topic(client, db, chair_headers, committee):
    """Type and topic live on the committee row, not on the chair, and both are shown."""
    committee.committee_type = "General Assembly"
    committee.topic = "Maritime security in the Gulf of Guinea"
    db.commit()

    response = client.get("/api/chair/committee/overview", headers=chair_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["chairName"] == "Chair Person"
    assert body["committeeName"] == "DISEC"
    assert body["committeeType"] == "General Assembly"
    assert body["topic"] == "Maritime security in the Gulf of Guinea"


def test_overview_returns_empty_strings_when_the_committee_has_no_type_or_topic(
    client, chair_headers
):
    """Both columns are optional; the page prints them as-is and supplies its own wording."""
    response = client.get("/api/chair/committee/overview", headers=chair_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["committeeType"] == ""
    assert body["topic"] == ""
