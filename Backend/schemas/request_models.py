"""
Request body schemas for the SCVMUN Platform API.

Field names are camelCase to match the JSON the frontend actually sends
(see Frontend-API-Contract.md and Frontend/src/views/).
"""

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
    Delegates to create, keyed by a display name such as "Lincoln High - #1".

    Each value is positional, matching the CLI's `FinalAssignments`:
    [committee, committeeType, country].
    """

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
