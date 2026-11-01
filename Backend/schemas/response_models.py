"""
Response body schemas for the SCVMUN Platform API.

Every model here mirrors a shape in Frontend-API-Contract.md. Declaring them as
`response_model` means FastAPI validates outgoing data and publishes the contract
at /docs, so a drift between backend and frontend shows up as a 500 here rather
than as a silently blank panel in the UI.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# --- Auth ---


class User(BaseModel):
    name: str
    role: str  # 'delegate' | 'advisor' | 'chair' | 'admin'


class LoginResponse(BaseModel):
    user: User
    token: str


# --- Delegate ---


class DelegateInfo(BaseModel):
    committee: str = ""
    country: str = ""


class ConferenceLink(BaseModel):
    text: str
    url: str


class GradedCriterion(BaseModel):
    """One rubric criterion, joined with the mark the chair awarded it."""

    id: int | str
    label: str
    score: float
    maxScore: float


class PositionPaper(BaseModel):
    status: str = "unsubmitted"  # 'unsubmitted' | 'submitted' | 'graded'
    score: int | str = ""  # display string, e.g. "18/20"
    feedback: str = ""  # the chair's written comments
    instructions: list[str] = []
    criteria: list[GradedCriterion] = []  # empty until the paper is graded


class DelegateAssignmentResponse(BaseModel):
    announcements: list[str] = []
    delegate: DelegateInfo
    conferenceLinks: list[ConferenceLink] = []
    positionPaper: PositionPaper


# --- Advisor ---


class AdvisorDelegate(BaseModel):
    id: int
    country: str
    committee: str
    paperStatus: str  # 'unsubmitted' | 'submitted' | 'graded'
    paperGrade: str | None = None
    hash: str
    registered: bool


class AdvisorDelegatesResponse(BaseModel):
    delegates: list[AdvisorDelegate]
    total: int


class SchoolInfo(BaseModel):
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    advisorName: str = ""
    advisorEmail: str = ""
    advisorPhone: str = ""
    headDelegateName: str = ""
    headDelegateEmail: str = ""
    headDelegatePhone: str = ""


class BillingInfo(BaseModel):
    invoiceUrl: str = ""
    paymentStatus: str = "unpaid"  # 'paid' | 'partially paid' | 'unpaid'


class ChecklistItem(BaseModel):
    """One line of the advisor's checklist: the shared label plus this school's tick."""

    label: str
    completed: bool = False


class AdvisorSchoolResponse(BaseModel):
    school: SchoolInfo
    billing: BillingInfo
    checklist: list[ChecklistItem] = []


# --- Chair ---


class TimelineEvent(BaseModel):
    label: str
    timestamp: str  # ISO-8601; the frontend parses this to derive event status


class Timeline(BaseModel):
    preConference: list[TimelineEvent] = []
    duringConference: list[TimelineEvent] = []


class CommitteeOverviewResponse(BaseModel):
    chairName: str
    committeeName: str
    delegatesRegistered: int
    totalDelegates: int
    papersGraded: int
    totalPapersSubmitted: int
    timeline: Timeline


class GradingRubricCriterion(BaseModel):
    id: int | str
    label: str
    maxScore: float


class GradingDelegate(BaseModel):
    """One row of the chair's grading roster.

    There is no `pdfUrl` on purpose: an iframe cannot send the Authorization header, so
    the view fetches /chair/papers/{id}/download as a blob through the API client and
    previews the object URL it gets back.
    """

    id: int
    country: str
    committee: str
    status: str  # 'unsubmitted' | 'submitted' | 'graded'
    submissionDate: str = ""  # ISO-8601 with a UTC offset; empty when nothing was uploaded
    totalScore: str = ""  # display string, e.g. "18/20"
    scores: dict[str, float] = {}
    comments: str = ""


class RubricLevel(BaseModel):
    score: float
    label: str
    description: str = ""


class AwardsRubricCriterion(BaseModel):
    id: int | str
    label: str
    levels: list[RubricLevel]


class AwardDelegate(BaseModel):
    id: int
    country: str
    committee: str
    assignedAward: str = "None"
    scores: dict[str, float] = {}
    totalScore: float | None = None


# --- Admin ---


class CommitteeCount(BaseModel):
    committee: str
    count: int


class StorageUsage(BaseModel):
    usedGb: float
    totalGb: float


class DowntimeEvent(BaseModel):
    id: int
    startTime: str
    endTime: str
    duration: str
    reason: str


class AdminDashboardStatsResponse(BaseModel):
    totalDelegates: int
    committeeCounts: list[CommitteeCount] = []
    storage: StorageUsage
    downtimeEvents: list[DowntimeEvent] = []


class PortHealth(BaseModel):
    name: str
    port: int
    status: str  # 'healthy' | 'unreachable'


# --- Admin: hash management & award reporting ---
# Shapes for the routes ported from the legacy CLI app (administrator.py). The CLI
# returned ad-hoc dicts (some with tuple values); on the platform they are modelled
# explicitly so /docs publishes them and the dashboard can render them directly.


class HashEntry(BaseModel):
    """One delegate account and its login hash."""

    name: str  # display key, e.g. "Lincoln High - #1" or "France (DISEC)"
    hash: str


class HashListResponse(BaseModel):
    hashes: list[HashEntry] = []


class DroppedDelegate(BaseModel):
    name: str
    hash: str  # the hash that was deleted along with the delegate


class DropDelegatesResponse(BaseModel):
    dropped: list[DroppedDelegate] = []


class AwardEntry(BaseModel):
    country: str
    award: str


class CommitteeAwards(BaseModel):
    committee: str
    awards: list[AwardEntry] = []


class AwardsOverviewResponse(BaseModel):
    committees: list[CommitteeAwards] = []


# --- Admin: announcements & conference links ---


class BroadcastEntry(BaseModel):
    """One announcement or conference link, as the admin editor sees it.

    `committee_name` is null when the line is addressed to every delegate. `starts_at`
    null means it is live already; `ends_at` null means it has no planned end.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # 'announcement' | 'link'
    body: str
    url: str | None = None
    committee_name: str | None = None
    position: int
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class BroadcastListResponse(BaseModel):
    broadcasts: list[BroadcastEntry] = []


# --- Admin: conference checklist ---


class ConferenceChecklistItem(BaseModel):
    """A checklist line as the labels editor sees it: no tick, because that is per school."""

    id: int
    label: str


class ConferenceChecklistResponse(BaseModel):
    items: list[ConferenceChecklistItem] = []


class SchoolChecklistItem(BaseModel):
    """A checklist line joined with one school's tick."""

    id: int
    label: str
    completed: bool = False


class SchoolChecklistResponse(BaseModel):
    """One school's checklist state. `school_name` is included so a script can confirm it
    addressed the school it meant to."""

    school_id: int
    school_name: str
    items: list[SchoolChecklistItem] = []


class SchoolEntry(BaseModel):
    """One school, for the progress picker and the school/advisor hash tooling.

    `advisor_hash` is the access code the advisor signs up with. Admin-only, so it is
    returned unmasked - the same way /admin/hashes returns the delegates' real hashes.
    """

    id: int  # schools.account_id, which is the advisor's account id
    name: str
    advisor_hash: str | None = None


class SchoolListResponse(BaseModel):
    schools: list[SchoolEntry] = []


class SchoolDetails(BaseModel):
    """Every editable column of one school (the row minus the advisor foreign key)."""

    school_name: str
    school_address: str
    city: str
    state: str
    zip_code: str
    advisor_name: str
    advisor_phone: str
    advisor_email: str
    head_delegate_name: str
    head_delegate_email: str
    head_delegate_phone: str
    payment_status: str
    invoiceURL: str | None = None


class SchoolDelegateEntry(BaseModel):
    """One delegate of a school, as the Existing Schools view shows it.

    `has_paper` is about the *file*, not the row: a paper row whose bytes went missing is
    exactly what an admin rebuilding a school needs to see.
    """

    account_id: int
    name: str  # accounts.name, e.g. "Lincoln High - #1"
    country: str
    committee: str
    hash: str
    paper_status: str  # 'unsubmitted' | 'submitted' | 'graded'
    paper_grade: str | None = None
    has_paper: bool = False


class SchoolDetailResponse(BaseModel):
    """One school and its delegates, for the per-school detail view."""

    id: int
    advisor_hash: str | None = None
    school: SchoolDetails
    delegates: list[SchoolDelegateEntry] = []


class CommitteeChairEntry(BaseModel):
    """One chair of a committee, with the login hash the admin has to hand over."""

    account_id: int
    name: str
    email: str
    hash: str


class CommitteeDelegateEntry(BaseModel):
    """One delegate in a committee. `school_name` matters because a committee spans schools."""

    account_id: int
    name: str  # accounts.name, e.g. "Lincoln High - #1"
    country: str
    school_name: str
    hash: str
    paper_status: str
    paper_grade: str | None = None
    has_paper: bool = False


class CommitteeDetailResponse(BaseModel):
    """One committee: what it is, who chairs it, and who is in it."""

    committee_name: str
    committee_type: str | None = None
    topic: str | None = None
    chairs: list[CommitteeChairEntry] = []
    delegates: list[CommitteeDelegateEntry] = []


class DelegateRemovedResponse(BaseModel):
    """What removing one delegate from a committee actually removed."""

    delegate: str
    school: str
    files_deleted: int


class SchoolDeletedResponse(BaseModel):
    """What a school deletion actually removed."""

    school: str
    delegates_deleted: int
    files_deleted: int


# --- Admin: conference timeline ---


class TimelineEntry(BaseModel):
    """One timeline event as the admin editor sees it."""

    id: int
    phase: str  # 'preConference' | 'duringConference'
    label: str
    starts_at: datetime  # naive UTC, as stored


class TimelineListResponse(BaseModel):
    events: list[TimelineEntry] = []
