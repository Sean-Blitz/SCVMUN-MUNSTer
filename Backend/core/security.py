from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
import hashlib
import secrets

# 1. Initialize the hasher (uses Argon2id defaults)
ph = PasswordHasher()

def hash_password(password: str) -> str:
    """Hash a password using Argon2id.

    Argon2 generates a fresh random salt internally on every call and embeds it,
    along with the cost parameters, in the returned string. So no separate salt
    column is needed - and hashing the same password twice gives two different
    strings, both of which verify.
    """
    return ph.hash(password)

def verify_password(password: str, hashed: Optional[str]) -> bool:
    """Verify a password against its stored hash.

    Returns False for every failure mode rather than raising, so a bad password
    surfaces as a clean 401 instead of an unhandled 500.
    """
    if not hashed:
        # Unclaimed account: password_hash stays NULL until /auth/register sets it.
        return False

    try:
        ph.verify(hashed, password)
        return True
    except VerificationError:
        # Wrong password. VerifyMismatchError is a subclass of this, so it is
        # covered here along with the other verification failures.
        return False
    except InvalidHashError:
        # The stored value is not a well-formed Argon2 hash: a corrupt row, or one
        # written before the algorithm/parameters changed. Treat as a failed login.
        return False

def new_token() -> str:
    """Mint an opaque session token to hand to the client. Never stored as-is."""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Deterministic digest of a session token, for storage and lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()