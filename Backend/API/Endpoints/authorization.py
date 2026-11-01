"""
These are the only routes with no role gate: they are how a client obtains a token.
"""
import re
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from schemas.request_models import LoginRequest
from schemas.response_models import LoginResponse, User
from API.dependencies import bearer_scheme, require_captcha
from crud.db import get_db, utcnow
from crud.database_schema import Account, AuthSession
import core.audit
import core.security

router = APIRouter(prefix="/auth", tags=["auth"])

# How long a freshly issued token stays valid. `sessions.expires_at` is NOT NULL,
# so every session row must be given one.
SESSION_TTL = timedelta(days=3)


def _start_session(db: Session, user: Account) -> str:
    """Log `user` in: persist a session row and return the raw token.

    The raw token is never stored - only its SHA-256 digest - so a database leak
    does not hand an attacker a usable token. The plaintext is returned to the
    caller and exists nowhere else afterwards.
    """
    token = core.security.new_token()

    db.add(
        AuthSession(
            account_id=user.id,
            token_hash=core.security.hash_token(token),
            expires_at=utcnow() + SESSION_TTL,
        )
    )
    user.last_login = utcnow()
    db.commit()

    return token

def _is_strong_password(password):
    # Requires: Min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>])[A-Za-z\d!@#$%^&*(),.?\":{}|<>]{8,}$"
    
    if re.fullmatch(pattern, password):
        return True
    return False

@router.post("/login", response_model=LoginResponse, dependencies=[Depends(require_captcha)])
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Exchange a delegate/advisor/chair/admin hash and password for a session token.

    Looks the account up by `payload.hash`, verifies `payload.password`, creates a
    session token, and returns {user, token}. Raises 401 with a clear message on
    failure (the frontend shows it in a toast).
    """
    statement = select(Account).where(Account.identifier == payload.hash)
    user = db.scalars(statement).first()

    if user is None:
        core.audit.technical(
            "login.failed", hash=core.audit.masked(payload.hash), reason="unknown_code"
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access code or password. Check if you have registered yet.")

    if not core.security.verify_password(payload.password, user.password_hash):
        # The response deliberately says the same thing either way; the log does not have
        # to, and "they have not registered yet" is the first thing to check when a
        # delegate swears their password is right.
        core.audit.technical(
            "login.failed",
            actor=core.audit.actor(user),
            hash=core.audit.masked(payload.hash),
            reason="unregistered" if user.password_hash is None else "bad_password",
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access code or password. Check if you have registered yet.")

    core.audit.technical("login.ok", actor=core.audit.actor(user))
    token = _start_session(db, user)

    # Build the small `User` model explicitly: Pydantic does not read attributes off
    # an arbitrary ORM object unless the model opts into `from_attributes`.
    return LoginResponse(user=User(name=user.name, role=user.role), token=token)


@router.post("/register", response_model=LoginResponse, dependencies=[Depends(require_captcha)])
def register(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Register the delegate/advisor/chair/admin identified by a hash, then log them in.

    A "hash" is pre-issued by the organizers/admin and already has an `accounts` row
    with `password_hash = NULL`; registering *claims* that row by setting a password.
    The role cannot be taken from the request, so it comes from the pre-issued row.
    The frontend redirects to `/{role}/dashboard` on success, so `user.role` must be
    one of the four role names - which the admin tooling guarantees when it mints rows.
    """
    statement = select(Account).where(Account.identifier == payload.hash)
    user = db.scalars(statement).first()

    if user is None:
        core.audit.technical(
            "register.failed", hash=core.audit.masked(payload.hash), reason="unknown_code"
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Unknown access code. Ask your advisor for a valid hash.",
        )

    if user.password_hash is not None:
        # 409, not 401: the frontend clears the session and bounces to / on any 401,
        # which would be a confusing way to say "you already have a password".
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This access code has already been registered. Log in instead.",
        )
    elif _is_strong_password(payload.password) is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Password must be at least 8 characters long and include at least one uppercase letter, one lowercase letter, one digit, and one special character.",
        )

    user.password_hash = core.security.hash_password(payload.password)
    core.audit.technical(
        "register.claimed", actor=core.audit.actor(user), hash=core.audit.masked(payload.hash)
    )

    token = _start_session(db, user)

    return LoginResponse(user=User(name=user.name, role=user.role), token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> Response:
    """
    Delete the session behind the presented token. Idempotent, and deliberately unguarded.

    No role check and no 401: logging out means "this token must stop working", so a
    second call, an already-expired token, or no token at all get the same `204`. Failing
    here would only make the client show an error while it is already signed out.

    Only the presented session is removed - other devices stay signed in. A token that is
    no longer valid has nothing to delete, which is why nothing is logged in that case: the
    audit trail records real revocations, not repeated logout clicks.
    """
    if credentials is not None:
        session = db.scalars(
            select(AuthSession).where(
                AuthSession.token_hash == core.security.hash_token(credentials.credentials)
            )
        ).first()

        if session is not None:
            account_id = session.account_id
            db.execute(delete(AuthSession).where(AuthSession.id == session.id))
            db.commit()
            core.audit.technical("logout.ok", account=account_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
