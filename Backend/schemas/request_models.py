"""
Request body schemas for the SCVMUN Platform API.

Field names are camelCase to match the JSON the frontend actually sends
(see Frontend-API-Contract.md and Frontend/src/views/).
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

# Bounds here mirror the VARCHAR limits in crud/database_schema.py. They exist so an
# over-long value is rejected with a readable 422 instead of reaching Postgres, which
# raises a DataError and came back as a 500 (SQLite silently ignored the limits, which is
# why this was invisible for so long).
#
# The split of responsibilities: these are *storage* limits, so they live in the model.
# Business rules that need their own wording - a blank checklist label, a duplicate line,
# an unsupported payment_status, a delegate triple that is not three items - stay in the
# endpoints, where they can return the 400 the admin UI already expects.
HASH_MAX = 100         # accounts.identifier
NAME_MAX = 100         # accounts.name, committees.committee_name, most people/place names
LABEL_MAX = 200        # conference_checklist.label, timeline_events.label
COUNTRY_MAX = 100      # delegates.country
PASSWORD_MAX = 200     # never stored raw; a cap keeps Argon2 from hashing megabytes

# [committee, committeeType, country] - committeeType has no column, so it gets the
# committee limit.
AssignmentValue = Annotated[str, Field(max_length=NAME_MAX)]


class LoginRequest(BaseModel):
    hash: Annotated[str, Field(max_length=HASH_MAX)]
    password: Annotated[str, Field(max_length=PASSWORD_MAX)]


class VerifyHashesRequest(BaseModel):
    password: Annotated[str | None, Field(max_length=PASSWORD_MAX)] = None


class GradeSubmissionRequest(BaseModel):
    delegateId: int
    scores: dict[str, float]
    totalScore: Annotated[str, Field(max_length=100)]  # "<earned>/<max>", e.g. "18/20"
    comments: Annotated[str, Field(max_length=500)] = ""  # delegates.paper_comments


class AwardAssignmentRequest(BaseModel):
    delegateId: int
    assignedAward: Annotated[str, Field(max_length=NAME_MAX)]  # delegates.assigned_award
    scores: dict[str, float]
    totalScore: float


# --- Admin: hash management ---
# Bodies for the /admin/hashes routes, ported from the legacy CLI app
# (schemas/incoming_models.py). Field names are camelCase like the rest of the
# frontend-facing API.


class SchoolRequest(BaseModel):
    """A new school and the advisor account that comes with it.

    Every field except `payment_status` and `invoiceURL` is required: the school row has
    NOT NULL columns for them, and an advisor cannot be reached without a phone or email.
    """
    school_name: Annotated[str, Field(max_length=100)]
    school_address: Annotated[str, Field(max_length=200)]
    city: Annotated[str, Field(max_length=100)]
    state: Annotated[str, Field(max_length=100)]
    zip_code: Annotated[str, Field(max_length=10)]
    advisor_name: Annotated[str, Field(max_length=100)]
    advisor_phone: Annotated[str, Field(max_length=20)]
    advisor_email: Annotated[str, Field(max_length=100)]
    head_delegate_name: Annotated[str, Field(max_length=100)]
    head_delegate_email: Annotated[str, Field(max_length=100)]
    head_delegate_phone: Annotated[str, Field(max_length=20)]
    # The allowed values are checked in POST /admin/schools so the admin UI gets the 400
    # listing them, rather than a generic validation message.
    payment_status: Annotated[str, Field(max_length=50)] = "unpaid"
    invoiceURL: Annotated[str | None, Field(max_length=300)] = None


class NewHashRequest(BaseModel):
    """
    Delegates to create, keyed by a display name such as "1".

    Each value is positional, matching the CLI's `FinalAssignments`:
    [committee, committeeType, country].
    """
    school_name: Annotated[str, Field(max_length=100)]
    # The triple's arity is checked in the endpoint (its message names the offending
    # delegate); only the per-string storage limit belongs here.
    finalAssignments: dict[str, list[AssignmentValue]]


class DelegateHashRequest(BaseModel):
    """Identify a single delegate by committee and country."""

    committee: Annotated[str, Field(max_length=NAME_MAX)]
    country: Annotated[str, Field(max_length=COUNTRY_MAX)]


class SchoolHashRequest(BaseModel):
    """Identify a school whose delegates all need fresh hashes."""

    school: Annotated[str, Field(max_length=100)]


class DropDelegatesRequest(BaseModel):
    """
    Delegates to remove and de-hash, as [country, committee, committeeType] triples.

    Mirrors the CLI's `CountryAndCommitteeList` payload.
    """

    countryAndCommitteeList: list[list[AssignmentValue]]


# --- Admin: announcements & conference links ---
# Bodies for the /admin/broadcasts routes. Timestamps are naive UTC, like the columns
# they land in (see crud/db.utcnow).


class BroadcastRequest(BaseModel):
    """Create one announcement or conference link."""

    kind: Annotated[str, Field(max_length=20)]  # 'announcement' | 'link'
    body: Annotated[str, Field(max_length=300)]
    url: Annotated[str | None, Field(max_length=300)] = None
    committee_name: Annotated[str | None, Field(max_length=100)] = None  # null = every delegate
    position: int = 0  # display order within the strip
    starts_at: datetime | None = None  # null = live immediately
    ends_at: datetime | None = None  # null = no planned end


class BroadcastUpdateRequest(BaseModel):
    """
    Partial edit of one broadcast: only the fields present in the JSON are applied.

    `kind` is fixed at creation, so changing a line between the announcement bar and
    the link strip means deleting it and creating it again.
    """

    body: Annotated[str | None, Field(max_length=300)] = None
    url: Annotated[str | None, Field(max_length=300)] = None
    committee_name: Annotated[str | None, Field(max_length=100)] = None
    position: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


# --- Admin: conference checklist ---


class ChecklistItemRequest(BaseModel):
    """
    One checklist line for the labels editor.

    `id` is omitted for a new line. Existing lines must send their id back, because that
    id is what every school's progress row points at - the server updates lines in place
    rather than replacing them, so ticking survives an edit.
    """

    id: int | None = None
    # Length, blank and duplicate rules live in the endpoint: they return the 400 the
    # contract documents, with messages the editor's toast shows as-is.
    label: Annotated[str, Field(max_length=LABEL_MAX)]


class ChecklistUpdateRequest(BaseModel):
    """The whole conference-wide checklist, in display order: lines not listed are removed."""

    items: list[ChecklistItemRequest]


class ChecklistProgressUpdate(BaseModel):
    """
    One line to tick or untick for a school.

    Identify the line by `id`, or by `label` when driving this from a script and reading
    the labels from GET /admin/schools/{id}/checklist. Send exactly one of the two.
    """

    id: int | None = None
    label: str | None = None
    completed: bool


class ChecklistProgressRequest(BaseModel):
    """A partial update: lines not listed keep whatever state they already have."""

    items: list[ChecklistProgressUpdate]


# --- Admin: conference timeline ---


class TimelineEventRequest(BaseModel):
    """One dated point on the conference schedule.

    `starts_at` is naive UTC (no timezone suffix), like every other timestamp the API
    accepts; an aware value is rejected rather than silently shifted.
    """

    phase: Annotated[str, Field(max_length=20)]  # 'preConference' | 'duringConference'
    label: Annotated[str, Field(max_length=LABEL_MAX)]
    starts_at: datetime


class TimelineUpdateRequest(BaseModel):
    """The whole timeline: the editor replaces it in one request, in any order (the
    server sorts by time)."""

    events: list[TimelineEventRequest]
