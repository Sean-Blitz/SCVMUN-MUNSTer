"""
Authentication endpoints (/auth/*) — Frontend-API-Contract.md §1.

These are the only routes with no role gate: they are how a client obtains a token.
"""

from fastapi import APIRouter, HTTPException, status

from schemas.request_models import LoginRequest
from schemas.response_models import LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """
    Exchange a delegate/advisor/chair/admin hash and password for a session token.

    TODO: look the account up by `payload.hash`, verify `payload.password`, create a
    session token, and return {user, token}. Raise 401 with a clear message on failure
    (the frontend shows it in a toast).
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Login is not implemented yet.")


@router.post("/register", response_model=LoginResponse)
def register(payload: LoginRequest) -> LoginResponse:
    """
    Register the delegate/advisor/chair/admin identified by a hash, then log them in.

    TODO: create the account, then behave as /auth/login. The frontend redirects to
    `/{role}/dashboard` on success, so `user.role` must be one of the four role names.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Registration is not implemented yet.")
