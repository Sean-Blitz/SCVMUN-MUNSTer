"""Creating a school, and the advisor account that comes with it.

A school is not a free-standing row: `schools.account_id` *is* its primary key, so every
school is one advisor's account plus the school's own details. Two places need to make that
pair - `POST /admin/schools` and `crud/bootstrap.py` - and they must produce identical rows,
so the sequence lives here rather than in either caller.

Nobody sets a password: the advisor account is created with `password_hash = NULL`, which is
exactly the "hash issued, not yet claimed" state that `POST /auth/register` consumes. The
advisor then signs up on the login screen like a delegate. That is also why the minted
identifier is the caller's responsibility to *show* - it is not recoverable from the UI.
"""

import secrets
from typing import Any

from sqlalchemy.orm import Session

from crud.database_schema import Account, School

# The columns a school row needs, other than the account it hangs off. Shared so the API
# and the bootstrap validate the same set.
SCHOOL_FIELDS = (
    "school_name",
    "school_address",
    "city",
    "state",
    "zip_code",
    "advisor_name",
    "advisor_phone",
    "advisor_email",
    "head_delegate_name",
    "head_delegate_email",
    "head_delegate_phone",
)

PAYMENT_STATUSES = ("paid", "partially paid", "unpaid")
DEFAULT_PAYMENT_STATUS = "unpaid"


def mint_hash() -> str:
    """A new login hash. Same format everywhere, so codes look alike in the UI."""
    return secrets.token_hex(8)


def missing_fields(values: dict[str, Any]) -> list[str]:
    """The required school fields that are absent or blank, in a stable order."""
    return [field for field in SCHOOL_FIELDS if not str(values.get(field) or "").strip()]


def create_school_with_advisor(
    db: Session,
    *,
    values: dict[str, Any],
    identifier: str | None = None,
) -> tuple[Account, School]:
    """Add (not commit) an advisor account and its school; return both.

    `values` must pass `missing_fields()` and carry a valid `payment_status` - callers
    validate first so they can answer with their own message. The advisor's password stays
    NULL so the row is claimable through registration, and `identifier` may be supplied to
    reproduce a known hash instead of minting one.
    """
    advisor_name = str(values["advisor_name"]).strip()
    code = identifier or mint_hash()

    advisor = Account(identifier=code, role="advisor", name=advisor_name)
    db.add(advisor)
    # The school uses advisor.id as its own primary key, so the id must exist first.
    db.flush()

    school = School(
        account_id=advisor.id,
        payment_status=str(values.get("payment_status") or DEFAULT_PAYMENT_STATUS),
        invoiceURL=values.get("invoiceURL") or None,
        **{field: str(values[field]).strip() for field in SCHOOL_FIELDS},
    )
    db.add(school)
    return advisor, school
