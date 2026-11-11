"""GET /chair/committee/overview — the chair's own committee panel.

The response is what the Committee Overview page renders: the chair's name, the committee's
identity (name, type, topic) and the counts behind the two progress lines. The timeline is
covered by its own shape elsewhere; these tests are about the committee row being joined in.
"""

from crud.database_schema import Chairs


def _chair_for(factory, committee, *, name="Chair Person", email="chair@example.test"):
    """A chair account plus its committee row; the overview joins them by committee name."""
    account = factory.account(role="chair", name=name, identifier=f"CHAIR-{name[:4]}")
    factory.db.add(
        Chairs(
            account_id=account.id,
            name=name,
            committee_name=committee.committee_name,
            email=email,
        )
    )
    factory.db.commit()
    return account


def test_overview_carries_the_committees_type_and_topic(client, factory, committee):
    """Type and topic live on the committee row, not on the chair, and both are shown."""
    chair = _chair_for(factory, committee)
    committee.committee_type = "General Assembly"
    committee.topic = "Maritime security in the Gulf of Guinea"
    factory.db.commit()

    response = client.get("/api/chair/committee/overview", headers=factory.headers(chair))

    assert response.status_code == 200
    body = response.json()
    assert body["chairName"] == "Chair Person"
    assert body["committeeName"] == "DISEC"
    assert body["committeeType"] == "General Assembly"
    assert body["topic"] == "Maritime security in the Gulf of Guinea"


def test_overview_returns_empty_strings_when_the_committee_has_no_type_or_topic(
    client, factory, committee
):
    """Both columns are optional; the page prints them as-is and supplies its own wording."""
    chair = _chair_for(factory, committee)

    response = client.get("/api/chair/committee/overview", headers=factory.headers(chair))

    assert response.status_code == 200
    body = response.json()
    assert body["committeeType"] == ""
    assert body["topic"] == ""
