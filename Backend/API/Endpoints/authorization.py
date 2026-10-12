"""
These are the only routes with no role gate: they are how a client obtains a token.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from schemas.request_models import LoginRequest
from schemas.response_models import LoginResponse, User
from crud.db import get_db
from crud.database_schema import Account, AuthSession
import core.security

router = APIRouter(prefix="/auth", tags=["auth"])

# How long a freshly issued token stays valid. `sessions.expires_at` is NOT NULL,
# so every session row must be given one.
SESSION_TTL = timedelta(days=3)

def _utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    The schema's timestamp columns are plain `Mapped[datetime]`, i.e. Postgres
    `timestamp without time zone`, so the whole app stores naive UTC. Keeping this
    in one helper stops aware and naive datetimes from being compared by accident
    (Python raises TypeError on `aware > naive`).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
            expires_at=_utcnow() + SESSION_TTL,
        )
    )
    user.last_login = _utcnow()
    db.commit()

    return token


@router.post("/login", response_model=LoginResponse)
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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access code or password. Check if you have registered yet.")

    if not core.security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access code or password. Check if you have registered yet.")

    token = _start_session(db, user)

    # Build the small `User` model explicitly: Pydantic does not read attributes off
    # an arbitrary ORM object unless the model opts into `from_attributes`.
    return LoginResponse(user=User(name=user.name, role=user.role), token=token)


@router.post("/register", response_model=LoginResponse)
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

    user.password_hash = core.security.hash_password(payload.password)

    token = _start_session(db, user)

    return LoginResponse(user=User(name=user.name, role=user.role), token=token)