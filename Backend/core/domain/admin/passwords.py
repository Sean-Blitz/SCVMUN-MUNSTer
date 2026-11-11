"""Admin use case: reset a password without changing the account's hash (§8.12).

A hash and a password are two different things on the same row:

    accounts.identifier     the code the organisers hand out ("hash")
    accounts.password_hash  the password its holder chose at first registration

Neither is derived from the other, and reissuing a hash deliberately leaves the password
alone - so "I forgot my password" needs its own operation. Reissuing the hash does not fix
it: the holder would get a new code that still asks for the password they do not remember.

Rather than inventing a password for them, this returns the account to the state it was
created in - `password_hash = NULL`. The existing hash then claims the row again through
`POST /auth/register` ("First-Time Register") and the holder picks a new password
themselves. That keeps the project's rule that an admin never knows a user's password, and
it means no new credential has to be handed out.

Live sessions are revoked as part of the reset: a reset that left them running would not
lock anyone out.
"""

from sqlalchemy.orm import Session

import core.audit
from core.domain import errors
from core.domain.admin.hashes import revoke_sessions
from crud.database_schema import Account
from schemas.response_models import PasswordResetResponse


def reset_password(db: Session, *, account_id: int, actor: str) -> PasswordResetResponse:
    """Clear one account's password and end its sessions; return the hash to claim it with.

    Refuses (409) when the account has never registered: there is no password to clear, and
    reporting success would suggest the admin had fixed something.
    """
    account = db.get(Account, account_id)
    if account is None:
        raise errors.AccountNotFound(account_id)

    if account.password_hash is None:
        raise errors.AccountNotRegistered(account.name)

    revoke_sessions(db, account.id)
    account.password_hash = None
    db.commit()

    core.audit.technical(
        "password.reset",
        actor=actor,
        account=account.id,
        role=account.role,
        name=account.name,
    )

    return PasswordResetResponse(name=account.name, role=account.role, hash=account.identifier)
