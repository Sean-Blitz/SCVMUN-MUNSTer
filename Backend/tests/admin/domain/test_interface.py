"""Domain tests for ``core.domain.admin.interface`` (§8.1–§8.3).

This module is mostly *formatting*, and formatting is where the dashboard silently goes wrong:

* storage is GiB to one decimal, matching ``df -h``;
* a downtime timestamp says "UTC" explicitly, because the server has no idea which timezone
  the browser is in;
* a duration is at most two units ("12m 30s", "3h 12m", "2d 4h");
* a CSV cell renders NULL as empty, a datetime as ISO-8601 with an offset, and JSONB as
  compact, sorted JSON - which is what makes two exports of an unchanged database identical.

``_probe_port`` is tested against a real listening socket, because a probe that always said
"unreachable" would look exactly like a healthy dashboard.
"""

import socket
from datetime import datetime, timedelta, timezone

import core.monitor
from core.domain.admin import interface
from crud.database_schema import Account, Base


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def test_gib_rounds_to_one_decimal():
    assert interface._gib(1024**3) == 1.0
    assert interface._gib(int(2.55 * 1024**3)) == 2.5
    assert interface._gib(0) == 0.0


def test_a_downtime_time_says_utc():
    """An unqualified "05:26" would be quietly wrong for anyone outside UTC."""
    moment = datetime(2026, 10, 4, 5, 26, tzinfo=timezone.utc)

    assert interface._display_time(moment) == "Oct 4, 05:26 UTC"


def test_a_downtime_time_is_converted_to_utc():
    other = timezone(timedelta(hours=2))
    moment = datetime(2026, 10, 4, 7, 26, tzinfo=other)

    assert interface._display_time(moment) == "Oct 4, 05:26 UTC"


def test_a_duration_uses_at_most_two_units():
    """Four cases for four branches: seconds, minutes, hours, days."""
    assert interface._display_duration(timedelta(seconds=45)) == "45s"
    assert interface._display_duration(timedelta(minutes=12, seconds=30)) == "12m 30s"
    assert interface._display_duration(timedelta(hours=3, minutes=12)) == "3h 12m"
    assert interface._display_duration(timedelta(days=2, hours=4)) == "2d 4h"


def test_a_csv_cell_renders_null_as_empty():
    """The CSV convention: an empty cell, not the string "None"."""
    assert interface._csv_cell(None) == ""


def test_a_csv_cell_renders_a_naive_datetime_as_utc_iso():
    """The column is naive UTC, so the export says so instead of looking local."""
    assert (
        interface._csv_cell(datetime(2026, 10, 4, 9, 0))
        == "2026-10-04 09:00:00+00:00"
    )


def test_a_csv_cell_renders_jsonb_as_compact_sorted_json():
    """Sorted keys are what make two exports of an unchanged database byte-identical."""
    assert interface._csv_cell({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert interface._csv_cell([1, 2]) == "[1,2]"


def test_a_csv_cell_leaves_scalars_alone():
    assert interface._csv_cell("France") == "France"
    assert interface._csv_cell(42) == 42


# ---------------------------------------------------------------------------
# The database export
# ---------------------------------------------------------------------------


def test_the_export_has_one_block_per_table(db):
    """The marker row and the header row are what make the file readable, not just parseable."""
    export = interface.database_csv(db)

    lines = export.payload.splitlines()
    assert export.tables == len(Base.metadata.sorted_tables)
    assert lines[0].lstrip("\ufeff") == "# accounts"
    assert "id" in lines[1]


def test_the_export_is_deterministic(db):
    """Two exports of an unchanged database must be byte-identical, or diffs are useless."""
    assert interface.database_csv(db).payload == interface.database_csv(db).payload


def test_the_export_counts_the_rows_it_wrote(db, factory):
    factory.account(role="delegate", identifier="COUNT-1")

    export = interface.database_csv(db)

    # One account row, plus whatever rows the fixtures created.
    assert export.rows >= 1
    assert "COUNT-1" in export.payload


def test_the_export_is_not_redacted(db, factory):
    """A backup that hid the access codes would be useless; the file is as sensitive as the DB."""
    account = factory.account(role="delegate", identifier="SECRET-CODE-1")

    assert account.identifier in interface.database_csv(db).payload


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def test_log_file_is_none_until_it_exists(db, monkeypatch, tmp_path):
    """None is a real answer - "nothing has happened yet" - not an error."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    assert interface.log_file("business") is None

    (tmp_path / "business.log").write_text("a line\n", encoding="utf-8")

    assert interface.log_file("business") == tmp_path / "business.log"


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


def test_a_listening_port_probes_healthy():
    """A real socket, because a probe that always failed would look like a healthy dashboard."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        assert interface._probe_port(port) is True


def test_a_closed_port_probes_unreachable():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # The socket is closed, so nothing is listening on that port any more.

    assert interface._probe_port(port) is False


def test_the_health_report_covers_the_configured_ports():
    report = interface.check_port_health()

    assert [(entry.port, entry.name) for entry in report] == list(interface.MONITORED_PORTS)
    assert len({entry.port for entry in report}) == len(interface.MONITORED_PORTS)
    assert all(entry.status in {"healthy", "unreachable"} for entry in report)


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


def test_the_stats_count_delegates_per_committee(db, factory, committee, school):
    unsc = factory.committee("UNSC")
    factory.new_delegate(committee, school, country="France")
    factory.new_delegate(committee, school, country="Spain")
    factory.new_delegate(unsc, school, country="Italy")

    stats = interface.get_dashboard_stats(db)

    assert stats.totalDelegates == 3
    assert [(entry.committee, entry.count) for entry in stats.committeeCounts] == [
        ("DISEC", 2),
        ("UNSC", 1),
    ]


def test_an_empty_database_reports_zero_delegates(db, monkeypatch, tmp_path):
    """``LOG_DIR`` is redirected so "no downtime" means a fresh install, not a lucky order."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    stats = interface.get_dashboard_stats(db)

    assert stats.totalDelegates == 0
    assert stats.committeeCounts == []
    assert stats.downtimeEvents == []


def test_storage_is_reported_in_gib(db):
    storage = interface.get_dashboard_stats(db).storage

    assert isinstance(storage.usedGb, float)
    assert isinstance(storage.totalGb, float)
    assert storage.totalGb > 0
    assert 0 <= storage.usedGb <= storage.totalGb


def test_a_recorded_outage_reaches_the_stats(db):
    """Outages are inferred from heartbeat gaps; the dashboard shows the last seven days.

    The reason is unique to this test: ``downtime.log`` accumulates for the whole session
    (nothing truncates it between tests), so the assertions are scoped to this line.
    """
    end = datetime.now(timezone.utc)
    core.monitor.record_outage(end - timedelta(minutes=5), end, "unique-recent-outage")

    events = [
        event
        for event in interface.get_dashboard_stats(db).downtimeEvents
        if event.reason == "unique-recent-outage"
    ]

    assert len(events) == 1
    assert events[0].duration == "5m 0s"
    assert events[0].startTime.endswith("UTC")
    assert events[0].endTime.endswith("UTC")


def test_an_old_outage_falls_outside_the_window(db):
    end = datetime.now(timezone.utc) - timedelta(days=30)
    core.monitor.record_outage(end - timedelta(minutes=5), end, "unique-ancient-outage")

    reasons = [event.reason for event in interface.get_dashboard_stats(db).downtimeEvents]

    assert "unique-ancient-outage" not in reasons
