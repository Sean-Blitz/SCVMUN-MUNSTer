"""
Shared FastAPI dependencies: bearer-token authentication and role-based access control.

The frontend attaches `Authorization: Bearer <token>` to every request
(Frontend/src/api/client.js) and has four roles, mirroring the Vue router's
`meta.roles`: delegate, advisor, chair, admin.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# auto_error=False so a missing header raises our own 401 with the {"message": ...}
# body the frontend expects, instead of FastAPI's default {"detail": ...}.
bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """The authenticated caller, resolved from the bearer token."""

    id: int
    name: str
    role: str  # 'delegate' | 'advisor' | 'chair' | 'admin'


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    """
    Resolve the bearer token into the user it belongs to.

    TODO: validate `credentials.credentials` against the session store created by
    /auth/login and return the matching account. Until then every authenticated
    request returns 401.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session token.")


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
