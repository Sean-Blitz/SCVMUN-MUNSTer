"""
Shared FastAPI dependencies: bearer-token authentication and role-based access control.

The frontend attaches `Authorization: Bearer <token>` to every request
(Frontend/src/api/client.js) and has four roles, mirroring the Vue router's
`meta.roles`: delegate, advisor, chair, admin.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core import captcha
from core.security import hash_token
from crud.database_schema import Account, AuthSession
from crud.db import get_db, utcnow

# auto_error=False so a missing header raises our own 401 with the {"message": ...}
# body the frontend expects, instead of FastAPI's default {"detail": ...}.
bearer_scheme = HTTPBearer(auto_error=False)

# The browser sends the Turnstile token here rather than in the JSON body, so the
# login/register contract does not change and non-browser clients simply omit it when the
# check is disabled.
CAPTCHA_HEADER = "X-Turnstile-Token"


class CurrentUser(BaseModel):
    """The authenticated caller, resolved from the bearer token."""

    id: int
    name: str
    role: str  # 'delegate' | 'advisor' | 'chair' | 'admin'


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    """
    Resolve the bearer token into the user it belongs to.

    The token itself is never stored - `core.security.hash_token` digests it at issue time -
    so this looks the digest up in `sessions` and joins the account. Expiry is checked here
    rather than by a cleanup job: a stale row is harmless as long as it cannot authenticate,
    and deleting it on the way through would turn every read into a write.

    One 401 message for "no such session" and "expired session" on purpose: telling a caller
    which of the two it is would confirm that a token was once valid.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")

    row = db.execute(
        select(Account, AuthSession.expires_at)
        .join(AuthSession, AuthSession.account_id == Account.id)
        .where(AuthSession.token_hash == hash_token(credentials.credentials))
    ).first()

    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session token.")

    account, expires_at = row

    # Naive UTC on both sides, like every other timestamp column (see crud.db.utcnow).
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session token.")

    return CurrentUser(id=account.id, name=account.name, role=account.role)


def require_roles(*roles: str):
    """
    Build a dependency that only lets the given roles through.

    Attach it to a router so the whole route group is gated in one place:

        router = APIRouter(dependencies=[Depends(require_roles("chair", "admin"))])

    Handlers that also need the caller's identity can inject
    `Depends(get_current_user)`; the result is cached per request, so this does
    not authenticate twice.
    """

    def guard(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You do not have permission to access this resource.",
            )
        return user

    return guard


def require_captcha(
    request: Request,
    token: Annotated[str | None, Header(alias=CAPTCHA_HEADER)] = None,
) -> None:
    """Require a valid Turnstile token on a pre-auth route.

    A no-op when no secret is configured, which is how development and the test suite run.
    Otherwise: a missing or rejected token is 400 ("complete the human check"), and a
    Cloudflare outage is 503 - failing closed, but telling the visitor the difference
    between "you failed" and "we could not check right now".

    Applied to /auth/login and /auth/register; everything else is behind a bearer token and
    does not need it.
    """
    if not captcha.enabled():
        return

    client_ip = request.client.host if request.client else None

    try:
        passed = captcha.verify(token, client_ip)
    except captcha.CaptchaUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The human check is unavailable right now. Please try again in a moment.",
        ) from None

    if not passed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please complete the human check and try again.",
        )
