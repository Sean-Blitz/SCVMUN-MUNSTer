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
