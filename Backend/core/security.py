from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

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