"""
Admin endpoints (/admin/*) — Frontend-API-Contract.md §8.

This module also hosts the delegate-hash tooling and award report that used to live in
the separate CLI app (`administrator.py`, now removed). The routes were ported here so
the web dashboard and any future tooling share one API surface, one session model, and
one set of request/response schemas; the `/hashes` and `/awards` paths are unchanged
apart from living under this router's `/admin` prefix.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from API.dependencies import CurrentUser, get_current_user, require_roles
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

# Canned hashes carried over from the CLI app. They keep the response shape stable for
# the dashboard until accounts are actually persisted (see the TODOs below).
_MOCK_HASHES = ("hash123abc", "hash456def")


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


@router.post("/hashes", response_model=HashListResponse, status_code=status.HTTP_201_CREATED)
def create_school_or_delegate_hashes(
    payload: NewHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> HashListResponse:
    """
    Register new schools/delegates and return the hash minted for each one.

    `payload.finalAssignments` maps a display name ("Lincoln High - #1") to
    [committee, committeeType, country]; the response echoes those names.

    TODO: create the accounts and persist each generated hash. The values below are the
    CLI's placeholders, cycled across the submitted entries.
    """
    hashes = [
        HashEntry(name=name, hash=_MOCK_HASHES[index % len(_MOCK_HASHES)])
        for index, name in enumerate(payload.finalAssignments)
    ]
    return HashListResponse(hashes=hashes)


@router.post("/hashes/regenerate/delegate", response_model=HashEntry)
def regenerate_delegate_hash(
    payload: DelegateHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> HashEntry:
    """
    Mint a fresh hash for one delegate, identified by committee + country.

    TODO: invalidate the old hash so the previous value can no longer log in.
    """
    return HashEntry(name=f"{payload.country} ({payload.committee})", hash="hash789ghi")


@router.post("/hashes/regenerate/school", response_model=HashListResponse)
def regenerate_school_hashes(
    payload: SchoolHashRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> HashListResponse:
    """
    Mint fresh hashes for every delegate in `payload.school`.

    TODO: replace the placeholder entries with the school's actual delegates.
    """
    return HashListResponse(
        hashes=[
            HashEntry(name="country (committee)", hash="hash012jkl"),
            HashEntry(name="country2 (committee2)", hash="hash345mno"),
        ]
    )


@router.delete("/hashes", response_model=DropDelegatesResponse)
def drop_delegates_and_delete_hashes(
    payload: DropDelegatesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DropDelegatesResponse:
    """
    Remove delegates and delete their hashes.

    `payload.countryAndCommitteeList` holds [country, committee, committeeType] triples,
    matching the CLI payload (and the rows the dashboard builds).

    TODO: delete the accounts and return the hashes that were actually revoked.
    """
    return DropDelegatesResponse(
        dropped=[
            DroppedDelegate(name="school - #1", hash="hash123abc"),
            DroppedDelegate(name="school - #2", hash="hash456def"),
        ]
    )


@router.get("/hashes", response_model=HashListResponse)
def list_hashes(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    schoolName: Annotated[str | None, Query(description="Limit the list to one school")] = None,
) -> HashListResponse:
    """
    Return delegate hashes, optionally narrowed to a single school.

    TODO: filter by `schoolName` and return the real (unmasked) hashes — this route is
    admin-only, so unlike /advisor/delegates there is nothing to mask.
    """
    return HashListResponse(
        hashes=[
            HashEntry(name="schoolName - #1", hash="hash123abc"),
            HashEntry(name="schoolName - #2", hash="hash456def"),
        ]
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
