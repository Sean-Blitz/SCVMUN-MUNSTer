"""
Admin endpoints (/admin/*) — Frontend-API-Contract.md §8.

This module also hosts the delegate-hash tooling and award report that used to live in
the separate CLI app (`administrator.py`, now removed). The routes were ported here so
the web dashboard and any future tooling share one API surface, one session model, and
one set of request/response schemas; the `/hashes` and `/awards` paths are unchanged
apart from living under this router's `/admin` prefix.
"""

import csv
import io
import json
import os
import secrets
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session
from crud.db import get_db, utcnow

from API.dependencies import CurrentUser, get_current_user, require_roles
import core.audit
import core.monitor
import core.storage
from core.controls import BROADCAST_LIMITS, TIMELINE_PHASES

from crud.database_schema import (Account,AuthSession,Base,Broadcast,
    ChecklistProgress,Committees,ConferenceChecklist,Delegates,
    School,TimelineEvent)
from schemas.request_models import (BroadcastRequest,BroadcastUpdateRequest,
    ChecklistProgressRequest,ChecklistUpdateRequest,DelegateHashRequest,DropDelegatesRequest,
    NewHashRequest,SchoolHashRequest,TimelineUpdateRequest)

from schemas.response_models import (AdminDashboardStatsResponse,AwardEntry,
    AwardsOverviewResponse,BroadcastEntry,BroadcastListResponse,
    CommitteeAwards,CommitteeCount,ConferenceChecklistItem,ConferenceChecklistResponse,
    DowntimeEvent,DropDelegatesResponse,DroppedDelegate,HashEntry,
    HashListResponse,PortHealth,SchoolChecklistItem,
    SchoolChecklistResponse,SchoolEntry,SchoolListResponse,StorageUsage,TimelineEntry,
    TimelineListResponse,)

router = APIRouter(prefix="/admin",tags=["admin"],dependencies=[Depends(require_roles("admin"))])

# --- Dashboard, diagnostics & exports (§8.1 – §8.3) ---

# The volume whose capacity the dashboard reports: the whole filesystem the application
# (container included) is running on. Point STORAGE_PATH at a data volume to report that
# instead, if uploads live somewhere with its own budget.
STORAGE_PATH = os.getenv("STORAGE_PATH", "/")

DOWNTIME_WINDOW_DAYS = 7


def _gib(value: int) -> float:
    """Bytes as GiB to one decimal, matching what `df -h` reports."""
    return round(value / (1024**3), 1)


def _display_time(moment: datetime) -> str:
    """A downtime timestamp for the dashboard, in UTC and saying so.

    The file records UTC and the server has no idea which timezone the browser is in, so
    an unqualified "05:26" would be quietly wrong for anyone outside it.
    """
    return f"{moment.astimezone(timezone.utc).strftime('%b')} {moment.astimezone(timezone.utc).day}, {moment.astimezone(timezone.utc).strftime('%H:%M')} UTC"


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


@router.get("/dashboard-stats", response_model=AdminDashboardStatsResponse)
def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdminDashboardStatsResponse:
    """
    Return delegate distribution, server storage usage, and the past week's downtime.

    Storage is the filesystem the app runs on (`STORAGE_PATH`), as used/total GiB.

    `downtimeEvents` comes from the heartbeat monitor (core.monitor): outages are inferred
    from gaps between beats, because nothing can report an outage while it is down. The
    times and durations are pre-formatted display strings in UTC - the frontend renders
    them verbatim - and an empty list is meaningful: it renders the "100% Uptime" message,
    which is also what a fresh install with no heartbeat data shows.
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
        storage = StorageUsage(
            usedGb=_gib(usage.used),
            totalGb=_gib(usage.total),
        )

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


# The services the port monitor probes, as (port, display name). A tuple rather than a
# dict so the display order is the order written here; ports must be unique because the
# frontend keys the list by port. Loopback, because these are the ports this server has
# open - 80/443 are nginx, 22 is sshd.
MONITORED_PORTS: tuple[tuple[int, str], ...] = ((22, "SSH"), (80, "HTTP"), (443, "HTTPS"))

PORT_PROBE_HOST = "127.0.0.1"

# Kept short: a refused connection returns immediately, but a filtered one waits this long,
# and the admin dashboard runs this check on every load.
PORT_PROBE_TIMEOUT_SECONDS = 1.0


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


@router.get("/ports/health", response_model=list[PortHealth])
def check_port_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PortHealth]:
    """
    Probe the configured service ports and report whether each is reachable.

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


def _log_response(kind: str, download_name: str) -> Response:
    """Stream one audit log as plain text.

    Never an HTTPException: the frontend saves whatever bytes arrive, so a JSON error body
    would be written into the downloaded .txt. A log that has not been written yet is an
    empty file, which is the honest answer for "nothing has happened".
    """
    path = core.audit.log_path(kind)
    if not path.is_file():
        return Response(content="", media_type="text/plain")
    # Streamed rather than read into memory: these files are never rotated, so they only
    # ever grow.
    return FileResponse(path, media_type="text/plain", filename=download_name)


@router.get("/logs/business.txt")
def download_business_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """Return the business log as a plain-text blob."""
    return _log_response("business", "business.log")


@router.get("/logs/technology.txt")
def download_technology_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """Return the technology log as a plain-text blob. See the note on the business log."""
    return _log_response("technical", "technology.log")


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


@router.get("/export/database.csv")
def export_database_csv(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> Response:
    """
    Return every table as one CSV: a `# <table>` marker row per table, then its column
    headers, then its rows, with a blank line between tables. The `#` keeps a marker
    distinguishable from a header row of a one-column table such as `committees`.

    The columns come from SQLAlchemy's metadata and the rows from `select(table)`, so a new
    column or table appears in the export without anyone maintaining a list here. Tables are
    written in dependency order (accounts before the rows that reference it) and each table's
    rows by primary key, so two exports of an unchanged database are byte-identical.

    This is a full dump: `accounts.password_hash`, `accounts.identifier` (the access codes)
    and `sessions.token_hash` are included verbatim, because an export that quietly redacted
    them would be useless for a backup. The file is therefore as sensitive as the database,
    and the download is recorded in the technical log.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    tables = Base.metadata.sorted_tables
    written = 0

    for table in tables:
        # "# name" rather than a bare name: a table with a single column would otherwise
        # produce a heading row identical to its own header row (committees, for one).
        writer.writerow([f"# {table.name}"])
        writer.writerow([column.name for column in table.columns])

        rows = db.execute(select(table).order_by(*table.primary_key.columns)).all()
        for row in rows:
            writer.writerow([_csv_cell(value) for value in row])
            written += 1

        writer.writerow([])

    # The BOM is what makes Excel open a UTF-8 file as UTF-8 (accents in names); Sheets
    # strips it. Without it, "José" arrives as mojibake on Windows.
    payload = "\ufeff" + buffer.getvalue()

    core.audit.technical(
        "db.exported",
        actor=core.audit.actor(user),
        tables=len(tables),
        rows=written,
        bytes=len(payload.encode("utf-8")),
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="scvmun-export-{stamp}.csv"'},
    )


# --- Delegate hashes (§8.4) ---
# Ported from the CLI app. The CLI only checked that a bearer token was present; here
# the router's dependency restricts the routes to admin sessions.
#
# Model: one Account per delegation (role='delegate') carries the login hash in
# `identifier`, and one Delegates row carries its country/committee/school. Double
# delegation partners (same committee + country) are one delegation, so they share the
# account and therefore the hash - the database never tracks which partner is which.


def _mint_hash() -> str:
    """Mint a fresh login hash for an account.
    """
    return secrets.token_hex(8)


def _display_name(school_name: str, key: str) -> str:
    """Turn a submitted key ("1") into the dashboard's label ("Lincoln High - #1")."""
    return f"{school_name} - #{key}"


def _get_school(db: Session, school_name: str) -> School:
    """Look a school up by name, or fail with a message the admin can act on."""
    school = db.scalars(select(School).where(School.school_name == school_name)).first()
    if school is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown school '{school_name}'. It must exist before its delegates can get hashes.",
        )
    return school


def _ensure_committee(db: Session, committee_name: str) -> None:
    """Create the committees row a delegate's FK points at, if it is not there yet."""
    if db.get(Committees, committee_name) is None:
        db.add(Committees(committee_name=committee_name))
        db.flush()  # visible to the next delegate that names the same committee


def _revoke_sessions(db: Session, account_id: int) -> None:
    """Delete every live token for an account.

    Deleting the account would cascade to `sessions` anyway, but a *reissued* hash must
    also kill the old sessions even though the account row survives.
    """
    db.execute(delete(AuthSession).where(AuthSession.account_id == account_id))


@router.post("/hashes", response_model=HashListResponse, status_code=status.HTTP_201_CREATED)
def create_school_or_delegate_hashes(
    payload: NewHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> HashListResponse:
    """
    Register new delegates for a school and return the hash minted for each one.

    `payload.school_name` names an existing school; its advisor account owns the new
    delegates. The keys of `payload.finalAssignments` are per-school display labels
    ("1", "2") and each value is positional: [committee, committeeType, country].
    `committeeType` has no column in the schema (leftover from the CLI's shape), so it
    is accepted and ignored.
    """
    if not payload.finalAssignments:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add at least one delegate.")

    for key, assignment in payload.finalAssignments.items():
        if len(assignment) != 3:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'Delegate "{key}" must be [committee, committeeType, country].',
            )

    school = _get_school(db, payload.school_name)

    # (committee, country) -> account minted in *this* request, so two rows describing
    # the same delegation (partners) end up sharing one hash.
    shared: dict[tuple[str, str], Account] = {}
    hashes: list[HashEntry] = []

    for key, (committee, _committee_type, country) in payload.finalAssignments.items():
        committee, country = committee.strip(), country.strip()
        if not committee or not country:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'Delegate "{key}" needs both a committee and a country.',
            )

        pair = (committee, country)
        account = shared.get(pair)

        if account is None:
            existing = db.scalars(
                select(Delegates).where(
                    Delegates.committee == committee, Delegates.country == country
                )
            ).first()
            if existing is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"{country} ({committee}) already has a hash. Use regenerate to issue a new one.",
                )

            _ensure_committee(db, committee)
            account = Account(
                identifier=_mint_hash(),
                role="delegate",
                name=_display_name(payload.school_name, key),
            )
            db.add(account)
            db.flush()  # populates account.id for the profile row below
            db.add(
                Delegates(
                    account_id=account.id,
                    country=country,
                    committee=committee,
                    school_id=school.account_id,
                )
            )
            shared[pair] = account

        hashes.append(
            HashEntry(name=_display_name(payload.school_name, key), hash=account.identifier)
        )

    db.commit()

    core.audit.technical(
        "hash.minted",
        actor=core.audit.actor(user),
        school=payload.school_name,
        count=len(hashes),
    )

    return HashListResponse(hashes=hashes)


@router.post("/hashes/regenerate/delegate", response_model=HashEntry)
def regenerate_delegate_hash(
    payload: DelegateHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> HashEntry:
    """
    Mint a fresh hash for one delegate, identified by committee + country.

    Note: double delegation partners share the same hash, so the database does not need
    to track which delegate is which. The frontend shows the same hash for both partners.

    The new hash replaces `Account.identifier`, so the previous value can no longer log
    in, and the delegate's live sessions are revoked.
    """
    delegate = db.scalars(
        select(Delegates).where(
            Delegates.committee == payload.committee, Delegates.country == payload.country
        )
    ).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No delegate found for {payload.country} ({payload.committee}).",
        )

    account = db.get(Account, delegate.account_id)
    if account is None:
        # Profile row with no account: nothing to reissue, and nothing can log in.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No account is attached to {payload.country} ({payload.committee}).",
        )

    _revoke_sessions(db, account.id)
    new_hash = _mint_hash()
    account.identifier = new_hash
    db.commit()

    core.audit.technical(
        "hash.reissued",
        actor=core.audit.actor(user),
        delegate=f"{payload.country} ({payload.committee})",
        hash=core.audit.masked(new_hash),
    )

    return HashEntry(name=f"{payload.country} ({payload.committee})", hash=new_hash)


@router.post("/hashes/regenerate/school", response_model=HashListResponse)
def regenerate_school_hashes(
    payload: SchoolHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> HashListResponse:
    """
    Mint fresh hashes for every delegate in `payload.school`.

    Each delegate's previous hash and live sessions are invalidated, exactly as in the
    single-delegate variant.
    """
    school = _get_school(db, payload.school)

    delegates = db.scalars(
        select(Delegates)
        .where(Delegates.school_id == school.account_id)
        .order_by(Delegates.committee, Delegates.country)
    ).all()

    hashes: list[HashEntry] = []
    for delegate in delegates:
        account = db.get(Account, delegate.account_id)
        if account is None:
            continue

        _revoke_sessions(db, account.id)
        new_hash = _mint_hash()
        account.identifier = new_hash
        hashes.append(
            HashEntry(name=f"{delegate.country} ({delegate.committee})", hash=new_hash)
        )

    db.commit()

    core.audit.technical(
        "hash.reissued",
        actor=core.audit.actor(user),
        school=payload.school,
        count=len(hashes),
    )

    return HashListResponse(hashes=hashes)


@router.delete("/hashes", response_model=DropDelegatesResponse)
def drop_delegates_and_delete_hashes(
    payload: DropDelegatesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> DropDelegatesResponse:
    """
    Remove delegates and delete their hashes.

    `payload.countryAndCommitteeList` holds [country, committee, committeeType] triples,
    matching the CLI payload (and the rows the dashboard builds). `committeeType` is not
    persisted, so it only has to be present. Triples that match no delegate are skipped:
    the response lists the hashes that were actually revoked.
    """
    for entry in payload.countryAndCommitteeList:
        if len(entry) != 3:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Each entry must be [country, committee, committeeType].",
            )

    dropped: list[DroppedDelegate] = []
    orphaned_files: list[str] = []

    for country, committee, _committee_type in payload.countryAndCommitteeList:
        delegates = db.scalars(
            select(Delegates).where(
                Delegates.country == country, Delegates.committee == committee
            )
        ).all()

        for delegate in delegates:
            account = db.get(Account, delegate.account_id)
            if account is not None:
                dropped.append(DroppedDelegate(name=account.name, hash=account.identifier))
                _revoke_sessions(db, account.id)

            # The paper rows go with the delegate, but their files do not: collect the paths
            # now and unlink them after the commit, so a failed delete leaves the files (and
            # the rows) intact rather than the other way round.
            for upload in delegate.position_papers:
                orphaned_files.append(upload.file_path)

            # Delete the profile row first and flush: its position-paper children are
            # removed by the ORM cascade, and there is no relationship between Account
            # and Delegates for the unit of work to order these two deletes by, so the
            # accounts row would otherwise be deleted while its profile row still
            # pointed at it.
            db.delete(delegate)
            db.flush()
            if account is not None:
                db.delete(account)

    db.commit()

    # Best-effort: the rows are gone, so a file that cannot be removed is only wasted disk.
    for stale in orphaned_files:
        core.storage.delete_paper(stale)

    core.audit.technical(
        "delegates.dropped",
        actor=core.audit.actor(user),
        count=len(dropped),
        delegates=", ".join(entry.name for entry in dropped) or "-",
    )
    # Same action, business view: the roster changed. Two lines, each log coherent.
    core.audit.business(
        "roster.dropped", actor=core.audit.actor(user), count=len(dropped)
    )

    return DropDelegatesResponse(dropped=dropped)


@router.get("/hashes", response_model=HashListResponse)
def list_hashes(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    schoolName: Annotated[str | None, Query(description="Limit the list to one school")] = None,
    db: Session = Depends(get_db),
) -> HashListResponse:
    """
    Return delegate hashes, optionally narrowed to a single school.

    Admin-only, so unlike /advisor/delegates there is nothing to mask: the real hashes
    come back. An unknown `schoolName` simply matches nothing.
    """
    stmt = (
        select(Account)
        .join(Delegates, Delegates.account_id == Account.id)
        .where(Account.role == "delegate")
        .order_by(Account.name)
    )
    if schoolName:
        stmt = stmt.join(School, School.account_id == Delegates.school_id).where(
            School.school_name == schoolName
        )

    accounts = db.scalars(stmt).all()
    return HashListResponse(
        hashes=[HashEntry(name=account.name, hash=account.identifier) for account in accounts]
    )


# --- Award report (§8.5) ---


@router.get("/awards", response_model=AwardsOverviewResponse)
def get_awards_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AwardsOverviewResponse:
    """
    Return every committee's award assignments as country + award pairs.

    This is the read-only conference-wide report the CLI exposed; the chair-facing,
    writable award routes stay in chairs.py (§7).

    TODO: aggregate the assignments stored by POST /chair/awards/{delegate_id}.
    """
    return AwardsOverviewResponse(
        committees=[
            CommitteeAwards(
                committee="CommitteeName",
                awards=[AwardEntry(country="CountryName", award="AwardName")],
            )
        ]
    )


# --- Announcements & conference links (§8.6) ---
# The lines the delegate dashboard renders. The caps in core.controls.BROADCAST_LIMITS
# are enforced here rather than in the schema because they depend on the schedule: a row
# that has not ended yet can still appear, so it holds a slot, and an expired one frees
# it. Counting that way makes the cap an upper bound on what any delegate can ever see
# at one instant, which is the whole point of the 2 + 1 / 2 + 3 split.


def _validate_broadcast(
    db: Session, kind: str, body: str, url: str | None, committee_name: str | None
) -> tuple[str, str | None, str | None]:
    """Normalise and check the fields shared by both kinds. Returns the cleaned values."""
    if kind not in BROADCAST_LIMITS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"kind must be one of: {', '.join(sorted(BROADCAST_LIMITS))}.",
        )

    body = (body or "").strip()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body cannot be empty.")

    url = (url or "").strip() or None
    if kind == "link" and url is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A conference link needs a url.")
    if kind == "announcement" and url is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An announcement cannot carry a url.")

    if committee_name is not None:
        committee_name = committee_name.strip() or None
        if committee_name is not None and db.get(Committees, committee_name) is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Unknown committee '{committee_name}'."
            )

    return body, url, committee_name


def _validate_window(starts_at, ends_at) -> None:
    """Reject an inverted schedule before the schema's CHECK constraint sees it."""
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ends_at must be after starts_at.")


def _slots_used(db: Session, kind: str, committee_name: str | None, exclude_id: int | None = None) -> int:
    """How many rows of this kind + target can still be shown (i.e. have not ended)."""
    target = (
        Broadcast.committee_name.is_(None)
        if committee_name is None
        else Broadcast.committee_name == committee_name
    )
    stmt = (
        select(func.count())
        .select_from(Broadcast)
        .where(
            Broadcast.kind == kind,
            target,
            or_(Broadcast.ends_at.is_(None), Broadcast.ends_at > utcnow()),
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Broadcast.id != exclude_id)
    return db.scalar(stmt) or 0


def _enforce_cap(
    db: Session, kind: str, committee_name: str | None, exclude_id: int | None = None
) -> None:
    """Refuse a create/edit that would put more lines in front of a delegate than fit."""
    cap = BROADCAST_LIMITS[kind]["global" if committee_name is None else "committee"]
    if _slots_used(db, kind, committee_name, exclude_id) >= cap:
        audience = "for every delegate" if committee_name is None else f"for {committee_name}"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"At most {cap} live {kind}s are allowed {audience}. Delete one first.",
        )


@router.get("/broadcasts", response_model=BroadcastListResponse)
def list_broadcasts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    kind: Annotated[str | None, Query(description="'announcement' or 'link'")] = None,
    db: Session = Depends(get_db),
) -> BroadcastListResponse:
    """List every broadcast, expired ones included: this is the editor's view."""
    if kind is not None and kind not in BROADCAST_LIMITS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"kind must be one of: {', '.join(sorted(BROADCAST_LIMITS))}.",
        )

    stmt = select(Broadcast).order_by(
        Broadcast.kind, Broadcast.committee_name, Broadcast.position, Broadcast.id
    )
    if kind is not None:
        stmt = stmt.where(Broadcast.kind == kind)

    return BroadcastListResponse(
        broadcasts=[BroadcastEntry.model_validate(row) for row in db.scalars(stmt).all()]
    )


@router.get("/committees", response_model=list[str])
def list_committees(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[str]:
    """Committee names, for the broadcast target picker (and any future picker)."""
    return list(
        db.scalars(select(Committees.committee_name).order_by(Committees.committee_name)).all()
    )


@router.post("/broadcasts", response_model=BroadcastEntry, status_code=status.HTTP_201_CREATED)
def create_broadcast(
    payload: BroadcastRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> BroadcastEntry:
    """Publish one announcement or conference link, if its target still has room."""
    body, url, committee_name = _validate_broadcast(
        db, payload.kind, payload.body, payload.url, payload.committee_name
    )
    _validate_window(payload.starts_at, payload.ends_at)

    # A row with no end date, or one in the future, can still appear, so it counts.
    if payload.ends_at is None or payload.ends_at > utcnow():
        _enforce_cap(db, payload.kind, committee_name)

    broadcast = Broadcast(
        kind=payload.kind,
        body=body,
        url=url,
        committee_name=committee_name,
        position=payload.position,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(broadcast)
    db.commit()
    db.refresh(broadcast)  # created_at is a server default, so it only exists post-insert

    core.audit.business(
        "broadcast.published",
        actor=core.audit.actor(user),
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )

    return BroadcastEntry.model_validate(broadcast)


@router.patch("/broadcasts/{broadcast_id}", response_model=BroadcastEntry)
def update_broadcast(
    broadcast_id: int,
    payload: BroadcastUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> BroadcastEntry:
    """
    Edit one broadcast. `kind` is fixed at creation.

    Only the fields present in the JSON are applied, so `"ends_at": null` clears the end
    date while omitting it leaves it alone.
    """
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No broadcast with id {broadcast_id}.")

    changes = payload.model_dump(exclude_unset=True)
    body, url, committee_name = _validate_broadcast(
        db,
        broadcast.kind,
        changes.get("body", broadcast.body),
        changes.get("url", broadcast.url),
        changes.get("committee_name", broadcast.committee_name),
    )
    starts_at = changes.get("starts_at", broadcast.starts_at)
    ends_at = changes.get("ends_at", broadcast.ends_at)
    _validate_window(starts_at, ends_at)

    # Re-check the cap against the *new* target and schedule: an edit can move a line to
    # a busier committee, or revive an expired one that was not holding a slot.
    if ends_at is None or ends_at > utcnow():
        _enforce_cap(db, broadcast.kind, committee_name, exclude_id=broadcast.id)

    broadcast.body = body
    broadcast.url = url
    broadcast.committee_name = committee_name
    broadcast.starts_at = starts_at
    broadcast.ends_at = ends_at
    broadcast.position = changes.get("position", broadcast.position)
    broadcast.updated_at = utcnow()
    db.commit()

    core.audit.business(
        "broadcast.edited",
        actor=core.audit.actor(user),
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )

    return BroadcastEntry.model_validate(broadcast)


@router.delete("/broadcasts/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_broadcast(
    broadcast_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Remove one broadcast outright: announcements keep no history."""
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No broadcast with id {broadcast_id}.")

    core.audit.business(
        "broadcast.withdrawn",
        actor=core.audit.actor(user),
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )
    db.delete(broadcast)
    db.commit()


# --- Conference checklist (§8.7) ---
# Two tables: conference_checklist holds the labels every school shares, and
# checklist_progress holds each school's ticks. They are joined for the advisor panel and
# for the per-school view below. Lines are reconciled by id - never deleted and
# re-inserted wholesale - because a line's id is what progress rows point at, so a
# rename must not silently wipe every school's tick.


MAX_CHECKLIST_ITEMS = 20
MAX_CHECKLIST_LABEL = 200


def _get_school_or_404(db: Session, school_id: int) -> School:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No school with id {school_id}.")
    return school


def _ordered_items(db: Session) -> list[ConferenceChecklist]:
    return list(
        db.scalars(
            select(ConferenceChecklist).order_by(
                ConferenceChecklist.position, ConferenceChecklist.id
            )
        ).all()
    )


def _school_checklist(db: Session, school: School) -> SchoolChecklistResponse:
    """One school's checklist: every shared label, plus that school's tick if it has one."""
    rows = db.execute(
        select(ConferenceChecklist, ChecklistProgress.completed)
        .outerjoin(
            ChecklistProgress,
            (ChecklistProgress.item_id == ConferenceChecklist.id)
            & (ChecklistProgress.school_id == school.account_id),
        )
        .order_by(ConferenceChecklist.position, ConferenceChecklist.id)
    ).all()

    return SchoolChecklistResponse(
        school_id=school.account_id,
        school_name=school.school_name,
        items=[
            SchoolChecklistItem(id=item.id, label=item.label, completed=bool(completed))
            for item, completed in rows
        ],
    )


@router.get("/schools", response_model=SchoolListResponse)
def list_schools(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolListResponse:
    """Every school, for the progress picker (and for a script that needs the ids)."""
    schools = db.scalars(select(School).order_by(School.school_name)).all()
    return SchoolListResponse(
        schools=[SchoolEntry(id=school.account_id, name=school.school_name) for school in schools]
    )


@router.get("/checklist", response_model=ConferenceChecklistResponse)
def get_checklist(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ConferenceChecklistResponse:
    """The shared checklist labels, in display order. Ticks are per school (§8.7.4)."""
    return ConferenceChecklistResponse(
        items=[
            ConferenceChecklistItem(id=item.id, label=item.label)
            for item in _ordered_items(db)
        ]
    )


@router.put("/checklist", response_model=ConferenceChecklistResponse)
def replace_checklist(
    payload: ChecklistUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ConferenceChecklistResponse:
    """
    Reconcile the shared checklist with the submitted lines, in display order.

    Lines that arrive with an id are updated in place, so their schools' ticks survive;
    lines with no id are created; lines that are absent are deleted, taking their progress
    with them. Labels must be unique (case-insensitively) so a script can address a line by
    name as well as by id.
    """
    if len(payload.items) > MAX_CHECKLIST_ITEMS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A checklist holds at most {MAX_CHECKLIST_ITEMS} items.",
        )

    existing = {item.id: item for item in _ordered_items(db)}

    seen_ids: set[int] = set()
    seen_labels: set[str] = set()
    prepared: list[tuple[ConferenceChecklist | None, str]] = []

    for position, entry in enumerate(payload.items, start=1):
        label = entry.label.strip()
        if not label:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Item {position} needs a label."
            )
        if len(label) > MAX_CHECKLIST_LABEL:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Item {position} is longer than {MAX_CHECKLIST_LABEL} characters.",
            )

        folded = label.casefold()
        if folded in seen_labels:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Item {position} repeats the label '{label}'."
            )
        seen_labels.add(folded)

        row: ConferenceChecklist | None = None
        if entry.id is not None:
            row = existing.get(entry.id)
            if row is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"No checklist item with id {entry.id}."
                )
            if entry.id in seen_ids:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Item id {entry.id} was sent twice."
                )
            seen_ids.add(entry.id)

        prepared.append((row, label))

    # Update and create in place, then delete whatever the payload left out.
    for position, (row, label) in enumerate(prepared):
        if row is None:
            db.add(ConferenceChecklist(label=label, position=position))
        else:
            row.label = label
            row.position = position

    for item_id, row in existing.items():
        if item_id not in seen_ids:
            db.delete(row)

    db.commit()

    core.audit.business(
        "checklist.updated",
        actor=core.audit.actor(user),
        lines=len(prepared),
    )

    return get_checklist(user, db)


@router.get("/schools/{school_id}/checklist", response_model=SchoolChecklistResponse)
def get_school_checklist(
    school_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolChecklistResponse:
    """The shared labels with this school's ticks - what its advisor sees, plus the ids."""
    return _school_checklist(db, _get_school_or_404(db, school_id))


@router.patch("/schools/{school_id}/checklist", response_model=SchoolChecklistResponse)
def update_school_checklist(
    school_id: int,
    payload: ChecklistProgressRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolChecklistResponse:
    """
    Tick or untick lines for one school, addressing each by id or by label.

    A partial update: lines that are not listed keep their current state, which is what
    makes this convenient to call from a script ("mark 'Pay the conference fee' done").
    The admin UI sends every line, which amounts to a full save. Returns the school's
    checklist as it stands afterwards.
    """
    school = _get_school_or_404(db, school_id)
    items = {item.id: item for item in _ordered_items(db)}
    by_label = {item.label.casefold(): item for item in items.values()}

    resolved: list[tuple[ConferenceChecklist, bool]] = []
    for position, entry in enumerate(payload.items, start=1):
        if (entry.id is None) == (entry.label is None):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Item {position} must give exactly one of id or label.",
            )

        if entry.id is not None:
            item = items.get(entry.id)
            if item is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"No checklist item with id {entry.id}."
                )
        else:
            item = by_label.get((entry.label or "").strip().casefold())
            if item is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    f"No checklist item labelled '{entry.label}'.",
                )

        resolved.append((item, bool(entry.completed)))

    # Upsert: the pair (school, item) is the primary key, so a second save updates the row.
    for item, completed in resolved:
        row = db.get(ChecklistProgress, (school.account_id, item.id))
        if row is None:
            db.add(
                ChecklistProgress(
                    school_id=school.account_id,
                    item_id=item.id,
                    completed=completed,
                    updated_at=utcnow(),
                )
            )
        else:
            row.completed = completed
            row.updated_at = utcnow()

    db.commit()

    core.audit.business(
        "checklist.progress",
        actor=core.audit.actor(user),
        school=school.school_name,
        ticked=sum(1 for _, completed in resolved if completed),
        cleared=sum(1 for _, completed in resolved if not completed),
    )

    return _school_checklist(db, school)


# --- Conference timeline (§8.8) ---
# One schedule shared by every committee, stored in timeline_events. There is no
# completion flag: the chair dashboard compares each event's time with the clock, which
# is why the API only ever stores and returns times, and why the list is always sorted
# ascending - the view uses the next event's time as the end of the current window.


MAX_TIMELINE_EVENTS = 30
MAX_TIMELINE_LABEL = 200


def _timeline_response(db: Session) -> TimelineListResponse:
    """Every timeline event, earliest first."""
    rows = db.scalars(
        select(TimelineEvent).order_by(TimelineEvent.starts_at, TimelineEvent.id)
    ).all()
    return TimelineListResponse(
        events=[
            TimelineEntry(
                id=row.id, phase=row.phase, label=row.label, starts_at=row.starts_at
            )
            for row in rows
        ]
    )


@router.get("/timeline", response_model=TimelineListResponse)
def get_timeline(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TimelineListResponse:
    """The conference schedule, earliest first. Empty until an admin fills it in."""
    return _timeline_response(db)


@router.put("/timeline", response_model=TimelineListResponse)
def replace_timeline(
    payload: TimelineUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TimelineListResponse:
    """
    Replace the conference schedule with the submitted events.

    Nothing else references an event, so this is a plain delete-then-insert in one
    transaction; the events come back sorted by time, not in the order they were sent.
    """
    if len(payload.events) > MAX_TIMELINE_EVENTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The timeline holds at most {MAX_TIMELINE_EVENTS} events.",
        )

    events: list[TimelineEvent] = []
    for position, entry in enumerate(payload.events, start=1):
        label = entry.label.strip()
        if not label:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Event {position} needs a label."
            )
        if len(label) > MAX_TIMELINE_LABEL:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Event {position} is longer than {MAX_TIMELINE_LABEL} characters.",
            )
        if entry.phase not in TIMELINE_PHASES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Event {position}: phase must be one of {', '.join(TIMELINE_PHASES)}.",
            )
        if entry.starts_at.tzinfo is not None:
            # The column is naive UTC; an aware value would land shifted by whatever the
            # database session's offset happens to be.
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Event {position}: send starts_at as naive UTC, with no timezone suffix.",
            )

        events.append(
            TimelineEvent(phase=entry.phase, label=label, starts_at=entry.starts_at)
        )

    db.execute(delete(TimelineEvent))
    db.add_all(events)
    db.commit()

    core.audit.business(
        "timeline.updated",
        actor=core.audit.actor(user),
        events=len(events),
    )

    return _timeline_response(db)
