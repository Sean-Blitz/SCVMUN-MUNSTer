"""
Admin endpoints (/admin/*) — Frontend-API-Contract.md §8.

This module also hosts the delegate-hash tooling and award report that used to live in
the separate CLI app (`administrator.py`, now removed). The routes were ported here so
the web dashboard and any future tooling share one API surface, one session model, and
one set of request/response schemas; the `/hashes` and `/awards` paths are unchanged
apart from living under this router's `/admin` prefix.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
from crud.database_schema import Account, AuthSession, Committees, Delegates, School
from crud.db import get_db
from schemas.request_models import (
    DelegateHashRequest,
    DropDelegatesRequest,
    NewHashRequest,
    SchoolHashRequest,
)
from schemas.response_models import (
    AdminDashboardStatsResponse,
    AwardEntry,
    AwardsOverviewResponse,
    CommitteeAwards,
    DropDelegatesResponse,
    DroppedDelegate,
    HashEntry,
    HashListResponse,
    PortHealth,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("admin"))],
)

# --- Dashboard, diagnostics & exports (§8.1 – §8.3) ---


@router.get("/dashboard-stats", response_model=AdminDashboardStatsResponse)
def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminDashboardStatsResponse:
    """
    Return delegate distribution, server storage usage, and the past week's downtime.

    TODO: `startTime`, `endTime` and `duration` are pre-formatted display strings — the
    frontend renders them verbatim. An empty `downtimeEvents` list is meaningful: it
    renders the "100% Uptime" message.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/ports/health", response_model=list[PortHealth])
def check_port_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PortHealth]:
    """
    Probe the configured service ports and report whether each is reachable.

    TODO: `status` must be exactly "healthy" or "unreachable" — any other value renders
    as unreachable in the UI. Ports must be unique, as they are the list key.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/logs/business.txt")
def download_business_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """
    Return the business log as a plain-text blob.

    TODO: return Response(content=..., media_type="text/plain"). Errors must not be
    returned as JSON here — the frontend saves whatever bytes come back as the .txt file.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/logs/technology.txt")
def download_technology_log(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """Return the technology log as a plain-text blob. See the note on the business log."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


@router.get("/export/database.csv")
def export_database_csv(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Response:
    """
    Return a CSV export of the database.

    TODO: return Response(content=..., media_type="text/csv"), ideally with a
    Content-Disposition header.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


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
