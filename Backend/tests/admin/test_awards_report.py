"""API tests for GET /admin/awards (§8.5): the conference-wide award report.

A read-only view over what chairs have assigned. The interesting rules are about what it
*leaves out*:

* ``"None"`` is the frontend's own "no award" marker, not an award;
* a NULL assignment means nothing has been decided yet;
* ``"Candidate"`` is kept, because the shortlist is a decision an admin may want to see while
  the committee is still deciding.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/admin/test_awards_report.py -v
"""

import pytest


def test_the_report_refuses_an_anonymous_caller(client):
    response = client.get("/api/admin/awards")

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


def test_the_report_is_admin_only(client, delegate_headers):
    """Chairs write awards (§7); the conference-wide read is the admin's."""
    response = client.get("/api/admin/awards", headers=delegate_headers)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


def test_the_report_is_empty_before_any_award_is_assigned(
    client, factory, admin_headers, committee, school
):
    factory.new_delegate(committee, school, country="France")

    assert client.get("/api/admin/awards", headers=admin_headers).json() == {"committees": []}


def test_assignments_are_grouped_by_committee_and_ordered(
    client, factory, admin_headers, committee, school
):
    """One query, grouped in Python: committees and countries both come back in order."""
    unsc = factory.committee("UNSC")
    factory.new_delegate(committee, school, country="Spain", assigned_award="Best Delegate")
    factory.new_delegate(committee, school, country="France", assigned_award="Candidate")
    factory.new_delegate(unsc, school, country="Italy", assigned_award="Honorable Mention")

    body = client.get("/api/admin/awards", headers=admin_headers).json()

    assert body["committees"] == [
        {
            "committee": "DISEC",
            "awards": [
                {"country": "France", "award": "Candidate"},
                {"country": "Spain", "award": "Best Delegate"},
            ],
        },
        {"committee": "UNSC", "awards": [{"country": "Italy", "award": "Honorable Mention"}]},
    ]


def test_none_is_not_an_award(client, factory, admin_headers, committee, school):
    """"None" is the frontend's "no award" marker, so a delegate holding it is invisible."""
    factory.new_delegate(committee, school, country="France", assigned_award="None")
    factory.new_delegate(committee, school, country="Spain", assigned_award="Candidate")

    body = client.get("/api/admin/awards", headers=admin_headers).json()

    assert [entry["country"] for entry in body["committees"][0]["awards"]] == ["Spain"]


def test_an_unassigned_delegate_is_invisible(client, factory, admin_headers, committee, school):
    """NULL means undecided; the report lists decisions, not delegates."""
    factory.new_delegate(committee, school, country="France")

    assert client.get("/api/admin/awards", headers=admin_headers).json()["committees"] == []


def test_a_committee_with_no_assignments_does_not_appear(
    client, factory, admin_headers, committee, school
):
    """The grouping is built from assignments, so an empty committee creates no entry."""
    factory.new_delegate(committee, school, country="France", assigned_award="Best Delegate")
    factory.new_delegate(factory.committee("UNSC"), school, country="Italy")

    body = client.get("/api/admin/awards", headers=admin_headers).json()

    assert [entry["committee"] for entry in body["committees"]] == ["DISEC"]
