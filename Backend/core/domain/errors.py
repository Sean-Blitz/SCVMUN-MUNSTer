"""Domain errors: what a use case can fail with, independent of HTTP.

The transport layer maps these to status codes (`API/Endpoints/delegates.py`). Nothing in
this package imports FastAPI or Starlette, so the same failures work from a test, a script
or a future CLI - and moving the domain out of `core/` later will not touch the endpoints.

Why exceptions here at all, when "not found" could just be `None`: the failures that need
more than a message carry data. A rate limit has a retry delay, an oversized paper has the
limit - the endpoint needs those to build `Retry-After` and the user-facing text, and an
HTTPException built in the domain would put that decision in the wrong layer.
"""


class DomainError(Exception):
    """Base class for every failure a use case reports."""


# --- delegate use cases ----------------------------------------------------------------


class DelegateNotFound(DomainError):
    """No delegate profile is attached to the account."""


class PaperNotSubmitted(DomainError):
    """The delegate has never uploaded a position paper."""


class PaperFileMissing(DomainError):
    """A paper row exists but its bytes are not on disk."""


class PaperAlreadyGraded(DomainError):
    """The paper has been graded, so it can no longer be replaced."""


class UploadRateLimited(DomainError):
    """Too many uploads inside the rolling window."""

    def __init__(self, limit: int, window_hours: int) -> None:
        super().__init__(f"more than {limit} uploads in {window_hours}h")
        self.limit = limit
        self.window_hours = window_hours


class NotAPdf(DomainError):
    """The submitted bytes do not start with the PDF signature."""


class PaperTooLarge(DomainError):
    """The submitted bytes exceed the configured paper limit."""

    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"paper larger than {limit_mb} MB")
        self.limit_mb = limit_mb


class PaperStorageFailed(DomainError):
    """The file could not be written to the upload directory."""


# --- chair use cases -------------------------------------------------------------------


class ChairNotFound(DomainError):
    """No chair profile is attached to the account.

    Admins can reach the chair routes but have no `chairs` row, so there is no committee to
    scope a roster, a grade or an award to.
    """


class DelegateNotInCommittee(DomainError):
    """The delegate id does not belong to the caller's committee."""


class RubricNotConfigured(DomainError):
    """The rubric is empty, so grading would store a meaningless 0/0."""


class ScoreCriterionUnknown(DomainError):
    """A submitted mark names a criterion the published rubric does not contain."""

    def __init__(self, criteria: tuple[str, ...]) -> None:
        super().__init__(f"unknown criteria: {', '.join(criteria)}")
        self.criteria = criteria


class ScoreOutOfRange(DomainError):
    """A mark sits outside 0..the criterion's maximum."""

    def __init__(self, label: str, maximum: str, got: str) -> None:
        super().__init__(f"{label} out of range: {got} of {maximum}")
        self.label = label
        self.maximum = maximum
        self.got = got


class CommentsTooLong(DomainError):
    """The grade comments exceed the column's width."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"comments longer than {limit}")
        self.limit = limit


class AwardNotAssignable(DomainError):
    """The requested award is not one a chair may hand out."""

    def __init__(self, allowed: tuple[str, ...]) -> None:
        super().__init__(f"not an assignable award; allowed: {', '.join(allowed)}")
        self.allowed = allowed


class AwardCriteriaUnscored(DomainError):
    """An official award needs every rubric criterion scored first."""

    def __init__(self, award: str, missing: tuple[str, ...]) -> None:
        super().__init__(f"{award} needs {', '.join(missing)}")
        self.award = award
        self.missing = missing


# --- advisor use cases -----------------------------------------------------------------


class SchoolNotFound(DomainError):
    """No school profile is attached to the account."""


class DelegateNotInSchool(DomainError):
    """The delegate id does not belong to the caller's school."""


class AccountMissing(DomainError):
    """The session names an account that no longer exists."""


class PasswordRejected(DomainError):
    """The re-authentication password for a credential reveal was wrong."""


# --- shared admin reference data -------------------------------------------------------


class UnknownSchool(DomainError):
    """A request named a school that does not exist."""

    def __init__(self, school_name: str) -> None:
        super().__init__(f"unknown school: {school_name}")
        self.school_name = school_name


class UnknownCommittee(DomainError):
    """A request named a committee that does not exist.

    Committees are never created on the fly: a typo used to produce a phantom committee with
    no chair, so the list is authoritative and the admin creates rows explicitly.
    """

    def __init__(self, committee_name: str) -> None:
        super().__init__(f"unknown committee: {committee_name}")
        self.committee_name = committee_name


class DelegateAssignmentNotFound(DomainError):
    """No delegate holds the requested committee + country pairing."""

    def __init__(self, country: str, committee: str) -> None:
        super().__init__(f"no delegate for {country} ({committee})")
        self.country = country
        self.committee = committee


class DelegateAccountMissing(DomainError):
    """A delegate profile exists but its account row does not, so nothing can log in."""

    def __init__(self, country: str, committee: str) -> None:
        super().__init__(f"no account for {country} ({committee})")
        self.country = country
        self.committee = committee


class NoAssignments(DomainError):
    """A hash request carried no delegates to mint."""


class BadAssignmentShape(DomainError):
    """One delegate entry was not [committee, country] (or the legacy three-item form)."""

    def __init__(self, key: str) -> None:
        super().__init__(f"bad assignment shape for {key!r}")
        self.key = key


class BadAssignmentValue(DomainError):
    """One delegate entry had a blank committee or country."""

    def __init__(self, key: str) -> None:
        super().__init__(f"blank committee or country for {key!r}")
        self.key = key


class DelegationAlreadyHasHash(DomainError):
    """That committee + country already has an account; reissue instead of minting."""

    def __init__(self, country: str, committee: str) -> None:
        super().__init__(f"{country} ({committee}) already has a hash")
        self.country = country
        self.committee = committee


# --- awards report ---------------------------------------------------------------------


class UnknownSchoolId(DomainError):
    """A request named a school id that does not exist."""

    def __init__(self, school_id: int) -> None:
        super().__init__(f"unknown school id: {school_id}")
        self.school_id = school_id


# --- broadcasts ------------------------------------------------------------------------


class InvalidBroadcastKind(DomainError):
    """The requested kind is not one of the configured broadcast kinds."""

    def __init__(self, kinds: tuple[str, ...]) -> None:
        super().__init__(f"not a broadcast kind: {', '.join(kinds)}")
        self.kinds = kinds


class EmptyBroadcastBody(DomainError):
    """The line's text is blank."""


class LinkNeedsUrl(DomainError):
    """A conference link was submitted without a url."""


class AnnouncementHasUrl(DomainError):
    """An announcement was submitted with a url; only links carry one."""


class InvertedWindow(DomainError):
    """A broadcast was scheduled to end at or before it starts."""


class BroadcastCapReached(DomainError):
    """The target already holds as many live lines as it may show at once."""

    def __init__(self, kind: str, cap: int, audience: str) -> None:
        super().__init__(f"{cap} live {kind}s already for {audience}")
        self.kind = kind
        self.cap = cap
        self.audience = audience


class BroadcastNotFound(DomainError):
    """No broadcast row with that id."""

    def __init__(self, broadcast_id: int) -> None:
        super().__init__(f"no broadcast {broadcast_id}")
        self.broadcast_id = broadcast_id


# --- checklist -------------------------------------------------------------------------


class TooManyChecklistItems(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"more than {limit} checklist items")
        self.limit = limit


class ChecklistPosition(DomainError):
    """A checklist line failed validation; `position` is its 1-based place in the request."""

    def __init__(self, position: int) -> None:
        super().__init__(f"checklist item {position}")
        self.position = position


class ChecklistLabelMissing(ChecklistPosition):
    """A line arrived with a blank label."""


class ChecklistLabelTooLong(ChecklistPosition):
    def __init__(self, position: int, limit: int) -> None:
        super().__init__(position)
        self.limit = limit


class ChecklistLabelRepeated(ChecklistPosition):
    def __init__(self, position: int, label: str) -> None:
        super().__init__(position)
        self.label = label


class ChecklistItemNeedsOneIdentifier(ChecklistPosition):
    """A progress entry gave both an id and a label, or neither."""


class ChecklistItemNotFound(DomainError):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"no checklist item {item_id}")
        self.item_id = item_id


class ChecklistItemSentTwice(DomainError):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"checklist item {item_id} sent twice")
        self.item_id = item_id


class ChecklistLabelNotFound(DomainError):
    def __init__(self, label: str) -> None:
        super().__init__(f"no checklist item labelled {label!r}")
        self.label = label


# --- timeline --------------------------------------------------------------------------


class TooManyTimelineEvents(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"more than {limit} timeline events")
        self.limit = limit


class TimelinePosition(DomainError):
    """A timeline event failed validation; `position` is its 1-based place in the request."""

    def __init__(self, position: int) -> None:
        super().__init__(f"timeline event {position}")
        self.position = position


class TimelineLabelMissing(TimelinePosition):
    """An event arrived with a blank label."""


class TimelineLabelTooLong(TimelinePosition):
    def __init__(self, position: int, limit: int) -> None:
        super().__init__(position)
        self.limit = limit


class TimelinePhaseInvalid(TimelinePosition):
    def __init__(self, position: int, phases: tuple[str, ...]) -> None:
        super().__init__(position)
        self.phases = phases


class TimelineTimestampAware(TimelinePosition):
    """The timestamp carried a timezone; the column is naive UTC."""


class PinnedEventRemoved(DomainError):
    """The submitted schedule dropped or renamed the conference-start line."""

    def __init__(self, label: str) -> None:
        super().__init__(f"pinned event removed: {label}")
        self.label = label


# --- shared admin form errors ----------------------------------------------------------


class BlankField(DomainError):
    """A field that must carry a value arrived blank."""

    def __init__(self, field: str) -> None:
        super().__init__(f"blank field: {field}")
        self.field = field


class NoChanges(DomainError):
    """A PATCH carried no fields at all."""


class CommitteeExists(DomainError):
    """A committee with that name already exists; names are the primary key."""

    def __init__(self, committee_name: str) -> None:
        super().__init__(f"committee exists: {committee_name}")
        self.committee_name = committee_name


class ChairNotInCommittee(DomainError):
    """The chair id does not belong to the committee in the path."""


# --- school form errors ----------------------------------------------------------------


class MissingSchoolFields(DomainError):
    """The create-school payload is missing required fields."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__(f"missing school fields: {', '.join(fields)}")
        self.fields = fields


class InvalidPaymentStatus(DomainError):
    """`payment_status` is not one of the statuses the onboarding flow accepts."""

    def __init__(self, options: tuple[str, ...]) -> None:
        super().__init__(f"invalid payment status: {', '.join(options)}")
        self.options = options


class SchoolExists(DomainError):
    """A school with that name already exists."""

    def __init__(self, school_name: str) -> None:
        super().__init__(f"school exists: {school_name}")
        self.school_name = school_name


class DelegateLabelsTooLong(DomainError):
    """Renaming the school would push a delegate label past the column's 100 characters."""


class ConfirmationMismatch(DomainError):
    """The `confirm` parameter did not repeat the school's name."""


class DelegatePairTaken(DomainError):
    """Another delegate already holds that committee + country pairing."""

    def __init__(self, country: str, committee: str) -> None:
        super().__init__(f"{country} ({committee}) already has a delegate")
        self.country = country
        self.committee = committee


# --- Rubrics (§8.11) ---------------------------------------------------------------------


class NothingToUpdate(DomainError):
    """A rubric save named neither rubric, so there is nothing to write."""


class RubricInvalid(DomainError):
    """A submitted rubric breaks a rule the domain, not the schema, has to enforce.

    The request schema owns types, lengths and positivity; this is for the rules that
    depend on the other entries (a repeated criterion id, which would make every mark
    filed under it ambiguous).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid rubric: {detail}")
        self.detail = detail


class RubricCriterionInUse(DomainError):
    """Dropping or renaming a criterion would orphan marks already recorded against its id.

    `id` is the key in `delegates.paper_rubric_grade` and `delegates.overall_rubric_scores`,
    so a save that removes one leaves stored marks pointing at a criterion that no longer
    exists: the delegate's breakdown silently loses that line, and re-grading cannot
    recover it. Refused unless the caller forces the save.
    """

    def __init__(self, orphaned: dict[str, dict[str, int]]) -> None:
        listed = "; ".join(
            f"{kind}: "
            + ", ".join(
                f"'{criterion_id}' ({count} marked)"
                for criterion_id, count in sorted(ids.items())
            )
            for kind, ids in sorted(orphaned.items())
        )
        super().__init__(
            f"These criteria already have recorded marks: {listed}. "
            "Saving would orphan them - resend with force to remove them anyway."
        )
        self.orphaned = orphaned


# --- Account credentials (§8.12) ---------------------------------------------------------


class AccountNotFound(DomainError):
    """No account row has that id."""

    def __init__(self, account_id: int) -> None:
        super().__init__(f"no account with id {account_id}")
        self.account_id = account_id


class AccountNotRegistered(DomainError):
    """The account still has no password, so there is nothing to reset."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name} has not registered yet - the hash is still unclaimed, so they can "
            "use First-Time Register with it as it is."
        )
        self.name = name
