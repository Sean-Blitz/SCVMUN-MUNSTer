"""Heartbeat-based downtime monitoring.

There is no uptime service to ask, so the application keeps its own evidence: a beat is
appended every `HEARTBEAT_SECONDS`, and the next beat decides whether the previous one was
too long ago.

    LOG_DIR/heartbeat.log   the last few beats, trimmed - used only to answer "when was the
                            last beat?" so it never grows.
    LOG_DIR/downtime.log    one line per detected outage, appended and never trimmed.
                            Outages are rare, so this stays tiny, and it is the file the
                            admin dashboard reads for its "past 7 days" report. Deriving
                            the report from heartbeat.log instead would lose an incident a
                            few beats after it ended.

An outage is inferred, not observed: nothing runs while the process is down. The evidence
is only that the gap between two beats is longer than `GAP_THRESHOLD_SECONDS`, which is why
that threshold is set above the interval - a normal `systemctl restart` or one starved
thread must not be recorded as downtime. The record says when the heartbeat stopped and
when it came back, which for a reboot is the honest answer: the API was unavailable.

Timestamps here are ISO-8601 with an explicit offset rather than the naive UTC the database
columns use. These files are read by a human and by this module only, so the ambiguity is
worth paying a few bytes to avoid.
"""

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Iterator, TextIO

from core.audit import log_dir

try:  # POSIX. On a platform without flock the lock degrades to a no-op (see _exclusive).
    import fcntl
except ImportError:  # pragma: no cover - Windows only
    fcntl = None  # type: ignore[assignment]

HEARTBEAT_FILE = "heartbeat.log"
DOWNTIME_FILE = "downtime.log"

# How often to beat, and how long a gap has to be before it counts as downtime. The
# threshold is two intervals: one missed beat is a hiccup, two is an outage.
HEARTBEAT_SECONDS = 30.0
GAP_THRESHOLD_SECONDS = 60.0

# Only the last few beats are kept: gap detection reads the final line and nothing else.
KEEP_BEATS = 5

# A gap this large is a clock jump (NTP stepping, a restored snapshot), not an outage, and
# recording a three-week downtime would poison the dashboard.
MAX_PLAUSIBLE_GAP = timedelta(days=30)

_thread: threading.Thread | None = None
_stop = threading.Event()


@dataclass(frozen=True)
class Outage:
    """One detected outage, as recorded in downtime.log."""

    start: datetime
    end: datetime
    reason: str
    line: int  # 1-based line number, stable across requests, used as the dashboard id

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def heartbeat_path() -> Path:
    return log_dir() / HEARTBEAT_FILE


def downtime_path() -> Path:
    return log_dir() / DOWNTIME_FILE


@contextmanager
def _exclusive(path: Path) -> Generator[TextIO]:
    """Hold an exclusive lock on `path` while reading and rewriting it.

    Every uvicorn worker runs its own heartbeat thread, and the trim step rewrites the
    file, so writers and readers have to be kept apart. The same handle is used to read,
    truncate and rewrite - rather than writing a temporary file and renaming it - because
    swapping the inode would leave the lock guarding a file nobody writes to any more.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield handle
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(moment: str) -> datetime | None:
    """Read a stamp back, tolerating a line that was hand-edited or truncated."""
    try:
        parsed = datetime.fromisoformat(moment)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def record_outage(start: datetime, end: datetime, reason: str) -> None:
    """Append one outage to downtime.log."""
    with _exclusive(downtime_path()) as handle:
        handle.seek(0, os.SEEK_END)
        handle.write(f"{_stamp(start)} {_stamp(end)} {reason}\n")


def beat(*, startup: bool = False, now: datetime | None = None) -> datetime | None:
    """Record one heartbeat, and record an outage if the previous beat is too old.

    Returns the beat's timestamp, or None when nothing was written because another worker
    beat within the last half-interval. `startup` marks the first beat after the process
    started, which is what distinguishes "the service was not running" from "this thread
    stalled while the service was up".
    """
    moment = now or datetime.now(timezone.utc)

    with _exclusive(heartbeat_path()) as handle:
        handle.seek(0)
        beats = [line.strip() for line in handle if line.strip()]

        last = _parse(beats[-1]) if beats else None

        # Another worker of the same deployment may have beaten a moment ago; several
        # threads feeding one file would shorten its useful lookback for no gain.
        if last is not None and (moment - last).total_seconds() < HEARTBEAT_SECONDS / 2:
            return None

        if last is not None:
            gap = moment - last
            if GAP_THRESHOLD_SECONDS <= gap.total_seconds() <= MAX_PLAUSIBLE_GAP.total_seconds():
                record_outage(
                    last,
                    moment,
                    "service restart" if startup else "heartbeat gap",
                )

        beats.append(_stamp(moment))
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(beats[-KEEP_BEATS:]) + "\n")

    return moment


def recent_outages(days: int = 7) -> list[Outage]:
    """Outages that started within the last `days`, newest first.

    A missing or unreadable file is not an error: it means nothing has been recorded, which
    is what a fresh install looks like and what the dashboard renders as 100% uptime.
    """
    try:
        lines = downtime_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    outages: list[Outage] = []

    for index, line in enumerate(lines, start=1):
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        start, end = _parse(parts[0]), _parse(parts[1])
        if start is None or end is None or start < cutoff:
            continue
        outages.append(Outage(start=start, end=end, reason=parts[2].strip(), line=index))

    return list(reversed(outages))


def _run(interval: float) -> None:
    first = True
    while not _stop.is_set():
        try:
            beat(startup=first)
        except Exception:
            # A monitor that can take the API down is worse than no monitor. Note this
            # swallows everything on purpose, including a full disk.
            pass
        first = False
        if _stop.wait(interval):
            return


def start(interval: float = HEARTBEAT_SECONDS) -> None:
    """Start the heartbeat thread. Idempotent, and a no-op if one is already running."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_run, args=(interval,), name="scvmun-heartbeat", daemon=True
    )
    _thread.start()


def stop(timeout: float = 2.0) -> None:
    """Ask the heartbeat thread to finish, so shutdown and --reload are clean."""
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout)
        _thread = None
