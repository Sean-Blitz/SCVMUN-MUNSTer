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
    id: int
    country: str
    committee: str
    status: str  # 'unsubmitted' | 'submitted' | 'graded'
    submissionDate: str = ""
    totalScore: str = ""
    scores: dict[str, float] = {}
    comments: str = ""
    pdfUrl: str = ""


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
