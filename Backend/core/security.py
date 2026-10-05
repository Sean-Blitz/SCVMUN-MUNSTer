from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import hashlib
import secrets

# 1. Initialize the hasher (uses Argon2id defaults)
ph = PasswordHasher()

def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    try:
        ph.verify(hashed, password)
        return True
    except VerifyMismatchError:
        return False

def new_token() -> str:
    """Mint an opaque session token to hand to the client. Never stored as-is."""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Deterministic digest of a session token, for storage and lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()