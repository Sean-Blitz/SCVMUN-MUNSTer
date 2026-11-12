"""
Admin endpoints (/admin/*) — Frontend-API-Contract.md §8.

This module also hosts the delegate-hash tooling and award report that used to live in
the separate CLI app (`administrator.py`, now removed). The routes were ported here so
the web dashboard and any future tooling share one API surface, one session model, and
one set of request/response schemas; the `/hashes` and `/awards` paths are unchanged
apart from living under this router's `/admin` prefix.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles

import core.audit
from core.domain.admin import awards as awards_domain
from core.domain.admin import broadcasts as broadcasts_domain
from core.domain.admin import committees as committees_domain
from core.domain import errors as domain_errors
from core.domain.admin import hashes as hashes_domain
from core.domain.admin import passwords as passwords_domain
from core.domain.admin import interface as interface_domain
from core.domain.admin import schedule as schedule_domain
from core.domain.admin import rubrics as rubrics_domain
from core.domain.admin import schools as schools_domain
from crud.db import get_db
from schemas.request_models import (
    BroadcastRequest, BroadcastUpdateRequest, ChairHashRequest, ChairRequest,
    ChairUpdateRequest, CommitteeRequest, CommitteeUpdateRequest, DelegateUpdateRequest,
    SchoolRequest, SchoolUpdateRequest, ChecklistProgressRequest, ChecklistUpdateRequest,
    BulkChecklistProgressRequest, DelegateHashRequest, NewHashRequest, RubricUpdateRequest,
    TimelineUpdateRequest,
)
from schemas.response_models import (
    AdminDashboardStatsResponse, AwardsOverviewResponse, BroadcastEntry,
    BroadcastListResponse, CommitteeChairEntry, CommitteeDetailResponse,
    ConferenceChecklistResponse, DelegateRemovedResponse, HashEntry, HashListResponse,
    BulkChecklistProgressResponse, PasswordResetResponse, PortHealth, SchoolChecklistResponse,
    SchoolDelegateEntry,
    SchoolDetailResponse, RubricResponse, SchoolDeletedResponse, SchoolEntry, SchoolListResponse,
    TimelineListResponse,
)



router = APIRouter(prefix="/admin",tags=["admin"],dependencies=[Depends(require_roles("admin"))])

# --- Dashboard, diagnostics & exports (§8.1 – §8.3) ---
# The data lives in core.domain.interface; these routes pick a media type and a name.


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
        which is also what a fresh install with no heartbeat data shows."""
    return interface_domain.get_dashboard_stats(db)


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
        dashboard triggers on every load, and it would bury the real events."""
    return interface_domain.check_port_health()


def _log_response(kind: str, download_name: str) -> Response:
    """Stream one audit log as plain text.

    Never an HTTPException: the frontend saves whatever bytes arrive, so a JSON error body
    would be written into the downloaded .txt. A log that has not been written yet is an
    empty file, which is the honest answer for "nothing has happened".
    """
    path = interface_domain.log_file(kind)
    if path is None:
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
        and the download is recorded in the technical log."""
    export = interface_domain.database_csv(db)

    core.audit.technical(
        "db.exported",
        actor=core.audit.actor(user),
        tables=export.tables,
        rows=export.rows,
        bytes=len(export.payload.encode("utf-8")),
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=export.payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="scvmun-export-{stamp}.csv"'},
    )


# --- Delegate hashes (§8.4) ---
# Logic lives in core.domain.hashes; the notes that used to head this section are there.


def _hash_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a hash domain failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.UnknownSchool):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown school '{exc.school_name}'. Create it with POST /admin/schools first.",
        )
    if isinstance(exc, domain_errors.UnknownCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown committee '{exc.committee_name}'. Create it on the Committees tab first.",
        )
    if isinstance(exc, domain_errors.NoAssignments):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "Add at least one delegate.")
    if isinstance(exc, domain_errors.BadAssignmentShape):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Delegate "{exc.key}" must be [committee, country].',
        )
    if isinstance(exc, domain_errors.BadAssignmentValue):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Delegate "{exc.key}" needs both a committee and a country.',
        )
    if isinstance(exc, domain_errors.DelegationAlreadyHasHash):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"{exc.country} ({exc.committee}) already has a hash. "
            "Use regenerate to issue a new one.",
        )
    if isinstance(exc, domain_errors.DelegateAssignmentNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No delegate found for {exc.country} ({exc.committee}).",
        )
    if isinstance(exc, domain_errors.DelegateAccountMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No account is attached to {exc.country} ({exc.committee}).",
        )
    if isinstance(exc, domain_errors.ChairNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "No chair has that account id.")
    if isinstance(exc, domain_errors.AccountMissing):
        return HTTPException(status.HTTP_404_NOT_FOUND, "That chair has no account.")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.post("/hashes", response_model=HashListResponse, status_code=status.HTTP_201_CREATED)
def create_delegate_hashes(
    payload: NewHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> HashListResponse:
    """
        Mint a login hash for each new delegate of an existing school.

        **This does not create the school.** The name is deliberate: the school, its advisor
        account and the advisor's own hash come from POST /admin/schools, because a school row
        needs details this request has no room for (address, advisor contacts, payment status).
        An unknown name is a 404 that points at that endpoint.

        `payload.school_name` names the existing school; its advisor account owns the new
        delegates. The keys of `payload.finalAssignments` are per-school display labels
        ("1", "2") and each value is positional: [committee, country]. The legacy CLI shape
        [committee, committeeType, country] is still accepted; a committee's type belongs to
        the committee row, so that middle item has no column and is ignored."""
    try:
        return hashes_domain.mint_delegate_hashes(
            db,
            school_name=payload.school_name,
            assignments=payload.finalAssignments,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _hash_error(exc) from exc


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
        in, and the delegate's live sessions are revoked."""
    try:
        return hashes_domain.reissue_delegate_hash(
            db,
            committee=payload.committee,
            country=payload.country,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _hash_error(exc) from exc


@router.post("/hashes/regenerate/chair", response_model=HashEntry)
def regenerate_chair_hash(
    payload: ChairHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> HashEntry:
    """
        Mint a fresh hash for one chair, identified by account id.

        Chairs have no committee+country pair to identify them by, so the account id is the key.
        The old hash stops working and the chair's live sessions are revoked."""
    try:
        return hashes_domain.reissue_chair_hash(
            db,
            account_id=payload.account_id,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _hash_error(exc) from exc


def _password_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a credential failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.AccountNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "No account has that id.")
    if isinstance(exc, domain_errors.AccountNotRegistered):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.post("/accounts/{account_id}/reset-password", response_model=PasswordResetResponse)
def reset_account_password(
    account_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> PasswordResetResponse:
    """
        Clear one account's password so its holder can choose a new one.

        A hash and a password are separate: reissuing a hash changes the login code and
        leaves the old password attached, which does not help someone who has forgotten it.
        This is the operation for that case. It sets `password_hash` back to NULL and ends
        the account's sessions, so the existing hash works with "First-Time Register" again -
        the holder sets the new password themselves, and the admin never sees one.

        `409` when the account has never registered (the hash is still unclaimed, so there
        is nothing to reset); `404` for an unknown account id. The returned `hash` is the
        code to hand back, unchanged."""
    try:
        return passwords_domain.reset_password(
            db, account_id=account_id, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _password_error(exc) from exc


@router.get("/hashes", response_model=HashListResponse)
def list_hashes(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    schoolName: Annotated[str | None, Query(description="Limit the list to one school")] = None,
    db: Session = Depends(get_db),
) -> HashListResponse:
    """
        Return delegate hashes, optionally narrowed to a single school.

        Admin-only, so unlike /advisor/delegates there is nothing to mask: the real hashes
        come back. An unknown `schoolName` simply matches nothing."""
    return hashes_domain.list_hashes(db, school_name=schoolName)


# --- Award report (§8.5) ---


@router.get("/awards", response_model=AwardsOverviewResponse)
def get_awards_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AwardsOverviewResponse:
    """
        Return every committee's award assignments as country + award pairs.

        This is the read-only conference-wide report the CLI exposed; the chair-facing,
        writable award routes stay in chairs.py (§7).

        TODO: aggregate the assignments stored by POST /chair/awards/{delegate_id}."""
    return awards_domain.get_awards_overview(db)


# --- Announcements & conference links (§8.6) ---
# Logic in core.domain.broadcasts, including why the caps count schedule-bound rows.


def _broadcast_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a broadcast domain failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.InvalidBroadcastKind):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"kind must be one of: {', '.join(exc.kinds)}.",
        )
    if isinstance(exc, domain_errors.EmptyBroadcastBody):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "body cannot be empty.")
    if isinstance(exc, domain_errors.LinkNeedsUrl):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, "A conference link needs a url."
        )
    if isinstance(exc, domain_errors.AnnouncementHasUrl):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, "An announcement cannot carry a url."
        )
    if isinstance(exc, domain_errors.UnknownCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown committee '{exc.committee_name}'."
        )
    if isinstance(exc, domain_errors.InvertedWindow):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, "ends_at must be after starts_at."
        )
    if isinstance(exc, domain_errors.BroadcastCapReached):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"At most {exc.cap} live {exc.kind}s are allowed {exc.audience}. "
            "Delete one first.",
        )
    if isinstance(exc, domain_errors.BroadcastNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, f"No broadcast with id {exc.broadcast_id}."
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.get("/broadcasts", response_model=BroadcastListResponse)
def list_broadcasts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    kind: Annotated[str | None, Query(description="'announcement' or 'link'")] = None,
    db: Session = Depends(get_db),
) -> BroadcastListResponse:
    """List every broadcast, expired ones included: this is the editor's view."""
    try:
        return broadcasts_domain.list_broadcasts(db, kind=kind)
    except domain_errors.DomainError as exc:
        raise _broadcast_error(exc) from exc


@router.post("/broadcasts", response_model=BroadcastEntry, status_code=status.HTTP_201_CREATED)
def create_broadcast(
    payload: BroadcastRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> BroadcastEntry:
    """Publish one announcement or conference link, if its target still has room."""
    try:
        return broadcasts_domain.create_broadcast(
            db,
            kind=payload.kind,
            body=payload.body,
            url=payload.url,
            committee_name=payload.committee_name,
            position=payload.position,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _broadcast_error(exc) from exc


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
        date while omitting it leaves it alone."""
    try:
        return broadcasts_domain.update_broadcast(
            db,
            broadcast_id,
            changes=payload.model_dump(exclude_unset=True),
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _broadcast_error(exc) from exc


@router.delete("/broadcasts/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_broadcast(
    broadcast_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Remove one broadcast outright: announcements keep no history."""
    try:
        broadcasts_domain.delete_broadcast(db, broadcast_id, actor=core.audit.actor(user))
    except domain_errors.DomainError as exc:
        raise _broadcast_error(exc) from exc


# --- Conference checklist (§8.7) ---
# Logic in core.domain.schedule, together with the timeline.


# --- Committees (§8.10) ---
# Logic in core.domain.committees, including the rename transaction.


def _committee_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a committee domain failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.UnknownCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown committee '{exc.committee_name}'. "
            "Create it on the Committees tab first.",
        )
    if isinstance(exc, domain_errors.BlankField):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{exc.field} cannot be blank."
        )
    if isinstance(exc, domain_errors.CommitteeExists):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"A committee named '{exc.committee_name}' already exists.",
        )
    if isinstance(exc, domain_errors.NoChanges):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "No changes were sent.")
    if isinstance(exc, domain_errors.ChairNotInCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "That chair is not part of this committee."
        )
    if isinstance(exc, domain_errors.AccountMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "That chair no longer exists."
        )
    if isinstance(exc, domain_errors.DelegateNotInCommittee):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "That delegate is not in this committee."
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.get("/committees", response_model=list[str])
def list_committees(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[str]:
    """Committee names, for the broadcast target picker (and any future picker)."""
    return committees_domain.list_committees(db)


@router.post("/committees", response_model=CommitteeDetailResponse, status_code=status.HTTP_201_CREATED)
def create_committee(
    payload: CommitteeRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeDetailResponse:
    """Create a committee. Its name is the primary key, so a duplicate is a 409."""
    try:
        return committees_domain.create_committee(
            db,
            name=payload.committee_name,
            committee_type=payload.committee_type,
            topic=payload.topic,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.get("/committees/{committee_name}", response_model=CommitteeDetailResponse)
def get_committee_detail(
    committee_name: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeDetailResponse:
    """One committee: its type and topic, its chairs with their hashes, and its delegates."""
    try:
        return committees_domain.get_committee_detail(db, committee_name)
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.patch("/committees/{committee_name}", response_model=CommitteeDetailResponse)
def update_committee(
    committee_name: str,
    payload: CommitteeUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeDetailResponse:
    """
        Rename a committee and/or edit its type and topic.

        Renaming is the delicate part: `delegates.committee`, `chairs.committee_name` and
        `broadcasts.committee_name` all reference this primary key and none of them cascade on
        update, so the rename inserts the new row, repoints all three, then removes the old row -
        one transaction, so a failure anywhere leaves the old name and its children intact."""
    try:
        return committees_domain.update_committee(
            db,
            committee_name,
            changes=payload.model_dump(exclude_unset=True),
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.post(
    "/committees/{committee_name}/chairs",
    response_model=CommitteeChairEntry,
    status_code=status.HTTP_201_CREATED,
)
def create_committee_chair(
    committee_name: str,
    payload: ChairRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeChairEntry:
    """
        Add a chair to a committee and issue their login hash.

        Same shape as creating a school's advisor: the account is created with
        `password_hash` NULL, so the chair claims the hash with "First-Time Register". Nothing
        else in the API creates a `chairs` row, which is why this exists."""
    try:
        return committees_domain.create_committee_chair(
            db,
            committee_name,
            name=payload.name,
            email=payload.email,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.patch(
    "/committees/{committee_name}/chairs/{account_id}", response_model=CommitteeChairEntry
)
def update_committee_chair(
    committee_name: str,
    account_id: int,
    payload: ChairUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommitteeChairEntry:
    """Edit a chair's name or email. The path's committee must own the chair."""
    try:
        return committees_domain.update_committee_chair(
            db,
            committee_name,
            account_id,
            changes=payload.model_dump(exclude_unset=True),
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.delete(
    "/committees/{committee_name}/chairs/{account_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_committee_chair(
    committee_name: str,
    account_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Remove a chair: the profile row and the account, which cascades their sessions."""
    try:
        committees_domain.delete_committee_chair(
            db, committee_name, account_id, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


@router.delete(
    "/committees/{committee_name}/delegates/{account_id}",
    response_model=DelegateRemovedResponse,
)
def delete_committee_delegate(
    committee_name: str,
    account_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> DelegateRemovedResponse:
    """
        Remove one delegate from a committee: their rows, their hash and their stored paper.

        The path's committee must own the delegate, so a wrong committee cannot remove someone
        else's delegate. Files are unlinked after the commit because the cascade removes rows,
        not bytes - the same ordering as removing a whole school."""
    try:
        return committees_domain.delete_committee_delegate(
            db, committee_name, account_id, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _committee_error(exc) from exc


# --- Schools (§8.7, §8.9) ---
# Logic in core.domain.schools, including the rename that rewrites delegate labels.


def _school_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a school domain failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.UnknownSchoolId):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, f"No school with id {exc.school_id}."
        )
    if isinstance(exc, domain_errors.UnknownSchool):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown school '{exc.school_name}'. Create it with POST /admin/schools first.",
        )
    if isinstance(exc, domain_errors.MissingSchoolFields):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Missing required school details: " + ", ".join(exc.fields) + ".",
        )
    if isinstance(exc, domain_errors.InvalidPaymentStatus):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "payment_status must be one of: " + ", ".join(exc.options) + ".",
        )
    if isinstance(exc, domain_errors.SchoolExists):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"A school named '{exc.school_name}' already exists.",
        )
    if isinstance(exc, domain_errors.BlankField):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{exc.field.replace('_', ' ')} cannot be blank.",
        )
    if isinstance(exc, domain_errors.DelegateLabelsTooLong):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That name is too long: the delegate labels would exceed 100 characters.",
        )
    if isinstance(exc, domain_errors.ConfirmationMismatch):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "To delete a school, `confirm` must repeat its current name exactly.",
        )
    if isinstance(exc, domain_errors.DelegateNotInSchool):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "That delegate is not part of this school."
        )
    if isinstance(exc, domain_errors.AccountMissing):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "That delegate no longer exists."
        )
    if isinstance(exc, domain_errors.DelegatePairTaken):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"{exc.country} ({exc.committee}) already has a delegate hash.",
        )
    if isinstance(exc, domain_errors.NoChanges):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "No changes were sent.")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.post("/schools", response_model=SchoolEntry, status_code=status.HTTP_201_CREATED)
def create_school(
    payload: SchoolRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolEntry:
    """
        Create a school and issue its advisor's login hash.

        A school cannot exist without an advisor - `schools.account_id` is the advisor's account
        id - so this creates both, with `password_hash` NULL: the advisor claims the hash through
        "First-Time Register" on the login screen, exactly as a delegate does. The hash is
        returned because this is the only moment the admin is guaranteed to see it.

        Hashes for the school's delegates come afterwards, from POST /admin/hashes."""
    try:
        return schools_domain.create_school(
            db, values=payload.model_dump(), actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _school_error(exc) from exc


@router.get("/schools", response_model=SchoolListResponse)
def list_schools(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolListResponse:
    """Every school, with its advisor's hash, for the progress picker and the hash tooling.

        The advisor hash is included so a code that was misplaced can be read back without a
        database query; admin-only, and the same exposure as GET /admin/hashes for delegates."""
    return schools_domain.list_schools(db)


@router.get("/schools/{school_id}", response_model=SchoolDetailResponse)
def get_school_detail(
    school_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolDetailResponse:
    """
        One school: every editable detail, the advisor's hash, and each delegate with its
        country, committee, hash and paper status.

        One request per selection rather than a dump of every school, so the Existing Schools
        view never loads more than the admin is looking at."""
    try:
        return schools_domain.get_school_detail(db, school_id)
    except domain_errors.DomainError as exc:
        raise _school_error(exc) from exc


@router.patch("/schools/{school_id}", response_model=SchoolDetailResponse)
def update_school(
    school_id: int,
    payload: SchoolUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolDetailResponse:
    """
        Apply the fields present in the body; leave the rest alone.

        Renaming is the one behaviour with a side effect: delegate labels are stored as
        "<school> - #<key>" in `accounts.name`, so the rename rewrites the ones that still carry
        the old prefix, or the hash lists would keep showing a school that no longer exists."""
    try:
        return schools_domain.update_school(
            db,
            school_id,
            changes=payload.model_dump(exclude_unset=True),
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _school_error(exc) from exc


@router.patch("/schools/{school_id}/delegates/{account_id}", response_model=SchoolDelegateEntry)
def update_school_delegate(
    school_id: int,
    account_id: int,
    payload: DelegateUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolDelegateEntry:
    """
        Move one delegate to a different country or committee.

        The school id in the path must own the delegate, so a wrong id cannot be used to edit
        another school's delegate. Country and committee are the only writable fields; the hash
        is reissued through POST /admin/hashes/regenerate/delegate instead of being typed."""
    try:
        return schools_domain.update_school_delegate(
            db,
            school_id,
            account_id,
            changes=payload.model_dump(exclude_unset=True),
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _school_error(exc) from exc


@router.delete("/schools/{school_id}", response_model=SchoolDeletedResponse)
def delete_school(
    school_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    confirm: Annotated[
        str, Query(description="Repeat the school's current name to confirm the deletion")
    ],
    db: Session = Depends(get_db),
) -> SchoolDeletedResponse:
    """
        Delete a school, its advisors and its delegates, and unlink their stored papers.

        `confirm` must repeat the school's name: the confirmation dialog lives in the browser,
        so the server checks intent itself rather than trusting that the UI asked.

        Order matters. `delegates.school_id -> schools` is NO ACTION, so the delegates have to
        go before the advisor account whose deletion cascades the school away. Papers are rows
        deleted by the ORM cascade but files unlinked here, because a cascade only removes rows."""
    try:
        return schools_domain.delete_school(
            db, school_id, confirm=confirm, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _school_error(exc) from exc


@router.get("/checklist", response_model=ConferenceChecklistResponse)
def get_checklist(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ConferenceChecklistResponse:
    """The shared checklist labels, in display order. Ticks are per school (§8.7.4)."""
    return schedule_domain.get_checklist(db)


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
        name as well as by id."""
    try:
        return schedule_domain.replace_checklist(
            db, items=payload.items, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _schedule_error(exc) from exc


@router.get("/schools/{school_id}/checklist", response_model=SchoolChecklistResponse)
def get_school_checklist(
    school_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SchoolChecklistResponse:
    """The shared labels with this school's ticks - what its advisor sees, plus the ids."""
    try:
        return schedule_domain.get_school_checklist(db, school_id)
    except domain_errors.DomainError as exc:
        raise _schedule_error(exc) from exc


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
        checklist as it stands afterwards."""
    try:
        return schedule_domain.update_school_checklist(
            db, school_id, items=payload.items, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _schedule_error(exc) from exc


@router.patch("/checklist/progress", response_model=BulkChecklistProgressResponse)
def update_checklists_bulk(
    payload: BulkChecklistProgressRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> BulkChecklistProgressResponse:
    """
        Tick or untick the same checklist lines for many schools in one request.

        `school_ids` omitted means every school - the dashboard's "select all schools" case,
        so a line can be closed for the whole conference in one action. Lines are addressed
        the same way the single-school route accepts them (id or label), and everything is
        written in one transaction: an unknown id or label rejects the whole call rather than
        leaving some schools ticked."""
    try:
        return schedule_domain.update_checklists_bulk(
            db,
            school_ids=payload.school_ids,
            items=payload.items,
            actor=core.audit.actor(user),
        )
    except domain_errors.DomainError as exc:
        raise _schedule_error(exc) from exc


# --- Conference timeline (§8.8) ---
# Logic in core.domain.schedule, together with the checklist.


def _schedule_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a checklist or timeline domain failure into its status code."""
    if isinstance(exc, domain_errors.TooManyChecklistItems):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A checklist holds at most {exc.limit} items.",
        )
    if isinstance(exc, domain_errors.ChecklistLabelMissing):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Item {exc.position} needs a label."
        )
    if isinstance(exc, domain_errors.ChecklistLabelTooLong):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Item {exc.position} is longer than {exc.limit} characters.",
        )
    if isinstance(exc, domain_errors.ChecklistLabelRepeated):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Item {exc.position} repeats the label '{exc.label}'.",
        )
    if isinstance(exc, domain_errors.ChecklistItemNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, f"No checklist item with id {exc.item_id}."
        )
    if isinstance(exc, domain_errors.ChecklistItemSentTwice):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Item id {exc.item_id} was sent twice."
        )
    if isinstance(exc, domain_errors.ChecklistItemNeedsOneIdentifier):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Item {exc.position} must give exactly one of id or label.",
        )
    if isinstance(exc, domain_errors.ChecklistLabelNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No checklist item labelled '{exc.label}'.",
        )
    if isinstance(exc, domain_errors.UnknownSchoolId):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, f"No school with id {exc.school_id}."
        )
    if isinstance(exc, domain_errors.TooManyTimelineEvents):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The timeline holds at most {exc.limit} events.",
        )
    if isinstance(exc, domain_errors.TimelineLabelMissing):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Event {exc.position} needs a label."
        )
    if isinstance(exc, domain_errors.TimelineLabelTooLong):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Event {exc.position} is longer than {exc.limit} characters.",
        )
    if isinstance(exc, domain_errors.TimelinePhaseInvalid):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Event {exc.position}: phase must be one of {', '.join(exc.phases)}.",
        )
    if isinstance(exc, domain_errors.TimelineTimestampAware):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Event {exc.position}: send starts_at as naive UTC, with no timezone suffix.",
        )
    if isinstance(exc, domain_errors.PinnedEventRemoved):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{exc.label}' is the conference's start and cannot be removed or renamed. "
            "Change its time instead.",
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.get("/timeline", response_model=TimelineListResponse)
def get_timeline(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TimelineListResponse:
    """The conference schedule, earliest first. Empty until an admin fills it in."""
    return schedule_domain.get_timeline(db)


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

        The pinned "Conference Start" row is the exception: its time is the conference's start
        and the target of the header countdown, so it can be re-dated but not removed or
        renamed. Because the payload carries no ids - events have no identity to preserve - it
        is matched by (phase, label), which is why the label is part of the rule."""
    try:
        return schedule_domain.replace_timeline(
            db, events=payload.events, actor=core.audit.actor(user)
        )
    except domain_errors.DomainError as exc:
        raise _schedule_error(exc) from exc


# --- Conference-wide rubrics (§8.11) -----------------------------------------------------
# Reads deliberately are not repeated here: GET /chair/rubric and GET /chair/awards/rubric
# are already open to admins (the chair router allows the "admin" role), so the editor reads
# the rubric from exactly the endpoints the graders use, and there is no second read route
# that could drift out of step with them.


def _rubric_error(exc: domain_errors.DomainError) -> HTTPException:
    """Translate a rubric failure into the status code the contract documents."""
    if isinstance(exc, domain_errors.RubricCriterionInUse):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, domain_errors.RubricInvalid):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, domain_errors.NothingToUpdate):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Send the paper rubric, the awards rubric, or both.",
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.put("/rubrics", response_model=RubricResponse)
def update_rubrics(
    payload: RubricUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    force: Annotated[
        bool,
        Query(
            description=(
                "Save even if a criterion being removed already has recorded marks. "
                "Those marks stay in the database but stop appearing in the breakdowns."
            )
        ),
    ] = False,
    db: Session = Depends(get_db),
) -> RubricResponse:
    """
        Replace the conference-wide grading rubrics.

        Both rubrics are whole documents: what is sent replaces what is stored, with no
        merging and no ids to match up. The keys are independent, so the paper editor can
        save without touching the awards rubric and vice versa; omitting both is a 400.

        `force` exists for one case. Every recorded mark is filed under a criterion `id`
        (`paper_rubric_grade`, `overall_rubric_scores`), so dropping or renaming a criterion
        that is already graded would strand real work: the delegate's breakdown silently
        loses that line. Such a save is refused with 409 and a list of the affected ids
        unless this flag is set.

        The response is a re-read of both rubrics - the same shapes GET /chair/rubric and
        GET /chair/awards/rubric publish - so the editor shows what the graders will see."""
    paper = None if payload.paper is None else [item.model_dump() for item in payload.paper]
    awards = None if payload.awards is None else [item.model_dump() for item in payload.awards]

    try:
        return rubrics_domain.replace(
            db,
            paper=paper,
            awards=awards,
            actor=core.audit.actor(user),
            force=force,
        )
    except domain_errors.DomainError as exc:
        raise _rubric_error(exc) from exc
