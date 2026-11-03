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
