"""PATCH /admin/checklist/progress — one tick applied to many schools.

The dashboard's "select all schools" sends no school_ids, which means every school. Everything
is written in one transaction, so a bad id rejects the whole call rather than half-ticking the
conference.

The admin account and its header come from ``admin_headers`` in ``tests/admin/conftest.py``.
"""

from crud.database_schema import ChecklistProgress, ConferenceChecklist


def _school(factory, name):
    """A school needs its own advisor account, which is the schools table's primary key."""
    advisor = factory.account(role="advisor", name=f"Advisor {name}")
    return factory.school(advisor, name=name)


def _line(factory, label="Pay the conference fee", position=0):
    item = ConferenceChecklist(label=label, position=position)
    factory.db.add(item)
    factory.db.commit()
    return item


def _ticked(factory, school, item):
    row = factory.db.get(ChecklistProgress, (school.account_id, item.id))
    return row.completed if row else None


def test_no_school_ids_means_every_school(client, factory, admin_headers):
    first = _school(factory, "Lincoln High")
    second = _school(factory, "Rival High")
    item = _line(factory)

    response = client.patch(
        "/api/admin/checklist/progress",
        json={"items": [{"id": item.id, "completed": True}]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"schools": 2, "lines": 1}
    assert _ticked(factory, first, item) is True
    assert _ticked(factory, second, item) is True


def test_school_ids_narrows_the_targets(client, factory, admin_headers):
    first = _school(factory, "Lincoln High")
    second = _school(factory, "Rival High")
    item = _line(factory)

    response = client.patch(
        "/api/admin/checklist/progress",
        json={"school_ids": [first.account_id], "items": [{"id": item.id, "completed": True}]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"schools": 1, "lines": 1}
    assert _ticked(factory, first, item) is True
    assert _ticked(factory, second, item) is None  # no row was created


def test_unticking_clears_the_line_for_every_school(client, factory, admin_headers):
    first = _school(factory, "Lincoln High")
    item = _line(factory)
    client.patch(
        "/api/admin/checklist/progress",
        json={"items": [{"id": item.id, "completed": True}]},
        headers=admin_headers,
    )

    response = client.patch(
        "/api/admin/checklist/progress",
        json={"items": [{"id": item.id, "completed": False}]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert _ticked(factory, first, item) is False


def test_an_unknown_school_rejects_the_whole_call(client, factory, admin_headers):
    first = _school(factory, "Lincoln High")
    item = _line(factory)

    response = client.patch(
        "/api/admin/checklist/progress",
        json={"school_ids": [first.account_id, 999999], "items": [{"id": item.id, "completed": True}]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert _ticked(factory, first, item) is None


def test_an_unknown_line_rejects_the_whole_call(client, factory, admin_headers):
    first = _school(factory, "Lincoln High")

    response = client.patch(
        "/api/admin/checklist/progress",
        json={"items": [{"id": 999999, "completed": True}]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert factory.db.query(ChecklistProgress).filter_by(school_id=first.account_id).count() == 0
