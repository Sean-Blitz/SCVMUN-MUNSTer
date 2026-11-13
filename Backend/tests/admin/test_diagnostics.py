"""API tests for the admin diagnostics and export routes (§8.1–§8.3).

These are the routes that answer "is the conference healthy, and what do I take away with
me". Each has a non-obvious contract:

* ``dashboard-stats`` counts delegates per committee and reports storage as GiB; an empty
  ``downtimeEvents`` is meaningful (it renders "100% Uptime");
* ``ports/health`` reports exactly ``healthy`` or ``unreachable``, on unique ports, and the
  result is never audited because the dashboard calls it on every load;
* the two log downloads are **always** ``text/plain`` - a JSON error body would be saved into
  the .txt file - and a log that was never written is an empty file, not a 404;
* the CSV export is a full dump (access codes included) and records the download in the
  technical log, because the file is as sensitive as the database.
"""

from datetime import datetime, timedelta, timezone

import pytest

import core.audit
import core.monitor

DIAGNOSTIC_ROUTES = [
    ("get", "/api/admin/dashboard-stats", {}),
    ("get", "/api/admin/ports/health", {}),
    ("get", "/api/admin/logs/business.txt", {}),
    ("get", "/api/admin/logs/technology.txt", {}),
    ("get", "/api/admin/export/database.csv", {}),
]


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,kwargs", DIAGNOSTIC_ROUTES)
def test_every_route_refuses_an_anonymous_caller(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"message": "Authentication required."}


@pytest.mark.parametrize("method,path,kwargs", DIAGNOSTIC_ROUTES)
def test_every_route_is_admin_only(client, delegate_headers, method, path, kwargs):
    """Server health, audit logs and a database dump are not a delegate's business."""
    response = getattr(client, method)(path, headers=delegate_headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {
        "message": "You do not have permission to access this resource."
    }


# ---------------------------------------------------------------------------
# GET /admin/dashboard-stats
# ---------------------------------------------------------------------------


def test_the_stats_count_delegates_per_committee(client, factory, admin_headers, committee, school):
    unsc = factory.committee("UNSC")
    factory.new_delegate(committee, school, country="France")
    factory.new_delegate(committee, school, country="Spain")
    factory.new_delegate(unsc, school, country="Italy")

    body = client.get("/api/admin/dashboard-stats", headers=admin_headers).json()

    assert body["totalDelegates"] == 3
    assert body["committeeCounts"] == [
        {"committee": "DISEC", "count": 2},
        {"committee": "UNSC", "count": 1},
    ]


def test_storage_is_reported_in_gib(client, admin_headers):
    """The volume is read from ``STORAGE_PATH``; both numbers are floats in GiB."""
    storage = client.get("/api/admin/dashboard-stats", headers=admin_headers).json()["storage"]

    assert isinstance(storage["usedGb"], float)
    assert isinstance(storage["totalGb"], float)
    assert storage["totalGb"] > 0
    assert 0 <= storage["usedGb"] <= storage["totalGb"]


def test_no_recorded_outage_reads_as_full_uptime(client, admin_headers):
    """An empty list is the "100% Uptime" state, including on a fresh install."""
    assert client.get("/api/admin/dashboard-stats", headers=admin_headers).json()[
        "downtimeEvents"
    ] == []


def test_a_recorded_outage_reaches_the_dashboard(client, admin_headers):
    """The monitor infers outages from heartbeat gaps; the dashboard reports the last week."""
    end = datetime.now(timezone.utc)
    core.monitor.record_outage(end - timedelta(minutes=5), end, "service restart")

    events = client.get("/api/admin/dashboard-stats", headers=admin_headers).json()[
        "downtimeEvents"
    ]

    assert len(events) == 1
    assert events[0]["reason"] == "service restart"
    # Pre-formatted display strings: the view renders them verbatim.
    assert {"id", "startTime", "endTime", "duration", "reason"} == set(events[0])


# ---------------------------------------------------------------------------
# GET /admin/ports/health
# ---------------------------------------------------------------------------


def test_the_port_probe_covers_the_monitored_services(client, admin_headers):
    """Three ports, unique, each with a status the view understands.

    The status is asserted by membership rather than by value: whether sshd or nginx is
    listening depends on the machine the suite runs on.
    """
    body = client.get("/api/admin/ports/health", headers=admin_headers).json()

    assert [(entry["port"], entry["name"]) for entry in body] == [
        (22, "SSH"),
        (80, "HTTP"),
        (443, "HTTPS"),
    ]
    assert len({entry["port"] for entry in body}) == 3
    assert all(entry["status"] in {"healthy", "unreachable"} for entry in body)


# ---------------------------------------------------------------------------
# GET /admin/logs/*
# ---------------------------------------------------------------------------


def test_the_business_log_downloads_as_plain_text(client, admin_headers):
    core.audit.business("grade.saved", actor="chair:1", total="18/20")

    response = client.get("/api/admin/logs/business.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "grade.saved" in response.text
    assert "business.log" in response.headers["content-disposition"]


def test_the_technology_log_downloads_as_plain_text(client, admin_headers):
    """The route is ``technology.txt`` but the file is ``technical.log`` - two names, one log."""
    core.audit.technical("login.ok", actor="delegate:1")

    response = client.get("/api/admin/logs/technology.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.text

    response = client.get("/api/admin/logs/technology.txt", headers=admin_headers)
    assert "technology.log" in response.headers["content-disposition"]


def test_a_log_that_was_never_written_is_an_empty_file(
    client, admin_headers, monkeypatch, tmp_path
):
    """200 with no bytes, not a 404: the frontend saves whatever arrives.

    A JSON error body here would be written into the downloaded .txt file.

    ``LOG_DIR`` is redirected rather than the real file deleted. The audit handler keeps an
    open descriptor, so unlinking the log would send every later line to an unlinked inode -
    the file would never reappear and every audit assertion in the session would fail.
    """
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    response = client.get("/api/admin/logs/business.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.text == ""


# ---------------------------------------------------------------------------
# GET /admin/export/database.csv
# ---------------------------------------------------------------------------


def test_the_export_is_a_csv_with_one_block_per_table(client, admin, admin_headers):
    """``# <table>`` markers, a header row, then the rows, with a blank line between tables."""
    response = client.get("/api/admin/export/database.csv", headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="scvmun-export-' in response.headers["content-disposition"]

    body = response.text
    # The UTF-8 BOM is what makes Excel open the file as UTF-8.
    assert body.startswith("\ufeff")
    assert "# accounts" in body
    assert "# delegates" in body
    # A full dump is deliberately unmasked, so the admin's own code is in there.
    assert admin.identifier in body


def test_the_export_is_audited(client, admin_headers):
    """The file is as sensitive as the database, so taking it is a recorded event."""
    before = core.audit.read("technical")

    client.get("/api/admin/export/database.csv", headers=admin_headers)

    written = core.audit.read("technical")[len(before):]
    assert "db.exported" in written
    assert "tables=" in written
