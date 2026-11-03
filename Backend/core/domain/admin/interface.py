"""Admin interface data: dashboard stats, service ports, and the three exports.

This is the "interface" side of the admin area rather than a business domain: what the
dashboard shows about the server, and the files an administrator downloads. It still
follows the same three rules as the other domain modules - no FastAPI/Starlette/`API.*`
imports, data in and data out (`dict`/models/`Path`/text, never a `Response`), and
`core.domain.errors` for failures.
"""

import csv
import io
import json
import os
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.audit
import core.monitor
from crud.database_schema import Base, Delegates
from schemas.response_models import (
    AdminDashboardStatsResponse,
    CommitteeCount,
    DowntimeEvent,
    PortHealth,
    StorageUsage,
)

# The volume whose capacity the dashboard reports: the whole filesystem the application
# (container included) is running on. Point STORAGE_PATH at a data volume to report that
# instead, if uploads live somewhere with its own budget.
STORAGE_PATH = os.getenv("STORAGE_PATH", "/")

DOWNTIME_WINDOW_DAYS = 7

# The services the port monitor probes, as (port, display name). A tuple rather than a
# dict so the display order is the order written here; ports must be unique because the
# frontend keys the list by port. Loopback, because these are the ports this server has
# open - 80/443 are nginx, 22 is sshd.
MONITORED_PORTS: tuple[tuple[int, str], ...] = ((22, "SSH"), (80, "HTTP"), (443, "HTTPS"))

PORT_PROBE_HOST = "127.0.0.1"

# Kept short: a refused connection returns immediately, but a filtered one waits this long,
# and the admin dashboard runs this check on every load.
PORT_PROBE_TIMEOUT_SECONDS = 1.0


def _gib(value: int) -> float:
    """Bytes as GiB to one decimal, matching what `df -h` reports."""
    return round(value / (1024**3), 1)


def _display_time(moment: datetime) -> str:
    """A downtime timestamp for the dashboard, in UTC and saying so.

    The file records UTC and the server has no idea which timezone the browser is in, so
    an unqualified "05:26" would be quietly wrong for anyone outside it.
    """
    utc = moment.astimezone(timezone.utc)
    return f"{utc.strftime('%b')} {utc.day}, {utc.strftime('%H:%M')} UTC"


def _display_duration(length: timedelta) -> str:
    """A downtime duration, at most two units: "45s", "12m 30s", "3h 12m", "2d 4h"."""
    seconds = int(length.total_seconds())
    if seconds < 60:
        return f"{seconds}s"

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"

    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"

    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


# --- Dashboard stats (§8.1) -------------------------------------------------------------


def get_dashboard_stats(db: Session) -> AdminDashboardStatsResponse:
    """Delegate distribution, server storage usage, and the past week's downtime.

    Storage is the filesystem the app runs on (`STORAGE_PATH`), as used/total GiB.

    `downtimeEvents` comes from the heartbeat monitor (core.monitor): outages are inferred
    from gaps between beats, because nothing can report an outage while it is down. The
    times and durations are pre-formatted display strings in UTC - the view renders them
    verbatim - and an empty list is meaningful: it renders the "100% Uptime" message, which
    is also what a fresh install with no heartbeat data shows.
    """
    total_delegates = db.scalar(select(func.count()).select_from(Delegates)) or 0

    counts = db.execute(
        select(Delegates.committee, func.count())
        .group_by(Delegates.committee)
        .order_by(Delegates.committee)
    ).all()

    try:
        usage = shutil.disk_usage(STORAGE_PATH)
    except OSError:
        # An unreadable path is a configuration mistake, not a reason to fail the whole
        # dashboard: report an empty bar rather than a 500.
        storage = StorageUsage(usedGb=0.0, totalGb=0.0)
    else:
        storage = StorageUsage(usedGb=_gib(usage.used), totalGb=_gib(usage.total))

    return AdminDashboardStatsResponse(
        totalDelegates=total_delegates,
        committeeCounts=[
            CommitteeCount(committee=committee, count=count) for committee, count in counts
        ],
        storage=storage,
        downtimeEvents=[
            DowntimeEvent(
                id=outage.line,
                startTime=_display_time(outage.start),
                endTime=_display_time(outage.end),
                duration=_display_duration(outage.duration),
                reason=outage.reason,
            )
            for outage in core.monitor.recent_outages(DOWNTIME_WINDOW_DAYS)
        ],
    )


# --- Service ports (§8.2) ---------------------------------------------------------------


def _probe_port(port: int) -> bool:
    """True when something is accepting TCP connections on `port`.

    A bare TCP handshake - no protocol is spoken - so it is the same test for SSH, HTTP
    and HTTPS. A closed port answers with a refusal at once; a filtered one stalls until
    the timeout, which is why the callers probe concurrently.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(PORT_PROBE_TIMEOUT_SECONDS)
        try:
            return probe.connect_ex((PORT_PROBE_HOST, port)) == 0
        except OSError:
            # Bad address family or similar: report unreachable rather than a 500.
            return False


def check_port_health() -> list[PortHealth]:
    """Probe the configured service ports and report whether each is reachable.

    `status` is exactly "healthy" or "unreachable" - the view treats anything else as
    unreachable - and the ports are unique because the frontend uses them as the list key.

    The probes run concurrently so the worst case is one timeout rather than one per port,
    and the result is deliberately not written to the audit log: this is a read that the
    dashboard triggers on every load, and it would bury the real events.
    """
    ports = [port for port, _ in MONITORED_PORTS]

    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        reachable = list(pool.map(_probe_port, ports))

    return [
        PortHealth(name=name, port=port, status="healthy" if ok else "unreachable")
        for (port, name), ok in zip(MONITORED_PORTS, reachable)
    ]


# --- Exports (§8.3) ---------------------------------------------------------------------


def log_file(kind: str) -> Path | None:
    """The audit log for `kind`, or None when it has never been written.

    None is a real answer - "nothing has happened yet" - and the endpoint turns it into an
    empty download rather than an error, because the frontend saves whatever bytes arrive.
    """
    path = core.audit.log_path(kind)
    return path if path.is_file() else None


def _csv_cell(value: Any) -> Any:
    """Render one database value as a CSV cell.

    Timestamps are naive UTC in the database, so they go out ISO-8601 with an explicit
    offset rather than as a bare local-looking string; JSONB becomes compact JSON in one
    cell; NULL becomes an empty cell, which is the CSV convention.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (dict, list)):
        # sort_keys so two exports of the same database are byte-identical.
        return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
    return value


@dataclass(frozen=True)
class CsvExport:
    """A finished export, with the counts the download route records in the audit log."""

    payload: str
    tables: int
    rows: int


def database_csv(db: Session) -> CsvExport:
    """Every table as one CSV document, with the table and row counts.

    A `# <table>` marker row per table, then its column headers, then its rows, with a blank
    line between tables. The `#` keeps a marker distinguishable from a header row of a
    one-column table such as `committees`.

    The columns come from SQLAlchemy's metadata and the rows from `select(table)`, so a new
    column or table appears in the export without anyone maintaining a list here. Tables are
    written in dependency order and each table's rows by primary key, so two exports of an
    unchanged database are byte-identical.

    This is a full dump: `accounts.password_hash`, `accounts.identifier` (the access codes)
    and `sessions.token_hash` are included verbatim, because an export that quietly redacted
    them would be useless for a backup. The file is therefore as sensitive as the database,
    and the caller records the download in the technical log.

    The UTF-8 BOM is prepended here rather than in the endpoint: it is what makes Excel open
    the file as UTF-8 (accents in names); Sheets strips it. Without it, "José" arrives as
    mojibake on Windows.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    tables = Base.metadata.sorted_tables
    written = 0

    for table in tables:
        writer.writerow([f"# {table.name}"])
        writer.writerow([column.name for column in table.columns])

        for row in db.execute(select(table).order_by(*table.primary_key.columns)).all():
            writer.writerow([_csv_cell(value) for value in row])
            written += 1

        writer.writerow([])

    return CsvExport(payload="\ufeff" + buffer.getvalue(), tables=len(tables), rows=written)
