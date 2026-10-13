"""
Request body schemas for the SCVMUN Platform API.

Field names are camelCase to match the JSON the frontend actually sends
(see Frontend-API-Contract.md and Frontend/src/views/).
"""

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    hash: str
    password: str


class VerifyHashesRequest(BaseModel):
    password: str


class GradeSubmissionRequest(BaseModel):
    delegateId: int
    scores: dict[str, float]
    totalScore: str  # "<earned>/<max>", e.g. "18/20"
    comments: str = ""


class AwardAssignmentRequest(BaseModel):
    delegateId: int
    assignedAward: str
    scores: dict[str, float]
    totalScore: float


# --- Admin: hash management ---
# Bodies for the /admin/hashes routes, ported from the legacy CLI app
# (schemas/incoming_models.py). Field names are camelCase like the rest of the
# frontend-facing API.


class NewHashRequest(BaseModel):
    """
    Delegates to create, keyed by a display name such as "1".

    Each value is positional, matching the CLI's `FinalAssignments`:
    [committee, committeeType, country].
    """
    school_name: str
    finalAssignments: dict[str, list[str]]


class DelegateHashRequest(BaseModel):
    """Identify a single delegate by committee and country."""

    committee: str
    country: str


class SchoolHashRequest(BaseModel):
    """Identify a school whose delegates all need fresh hashes."""

    school: str


class DropDelegatesRequest(BaseModel):
    """
    Delegates to remove and de-hash, as [country, committee, committeeType] triples.

    Mirrors the CLI's `CountryAndCommitteeList` payload.
    """

    countryAndCommitteeList: list[list[str]]


# --- Admin: announcements & conference links ---
# Bodies for the /admin/broadcasts routes. Timestamps are naive UTC, like the columns
# they land in (see crud/db.utcnow).


class BroadcastRequest(BaseModel):
    """Create one announcement or conference link."""

    kind: str  # 'announcement' | 'link'
    body: str
    url: str | None = None
    committee_name: str | None = None  # null = every delegate
    position: int = 0  # display order within the strip
    starts_at: datetime | None = None  # null = live immediately
    ends_at: datetime | None = None  # null = no planned end


class BroadcastUpdateRequest(BaseModel):
    """
    Partial edit of one broadcast: only the fields present in the JSON are applied.

    `kind` is fixed at creation, so changing a line between the announcement bar and
    the link strip means deleting it and creating it again.
    """

    body: str | None = None
    url: str | None = None
    committee_name: str | None = None
    position: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
