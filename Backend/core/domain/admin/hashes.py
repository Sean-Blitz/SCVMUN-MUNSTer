"""Admin use cases for login hashes (§8.4).

Model: one Account per delegation (role='delegate') carries the login hash in `identifier`,
and one Delegates row carries its country/committee/school. Double delegation partners (same
committee + country) are one delegation, so they share the account and therefore the hash -
the database never tracks which partner is which.

Same three rules as the other domain modules: no FastAPI/Starlette/`API.*` imports, ids and
data in and out (never a `Response`), and `core.domain.errors` for failures.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import core.audit
import crud.onboarding as onboarding
from core.domain.admin.committees import require_committee
from core.domain.errors import (
    AccountMissing,
    BadAssignmentShape,
    BadAssignmentValue,
    ChairNotFound,
    DelegateAccountMissing,
    DelegateAssignmentNotFound,
    DelegationAlreadyHasHash,
    NoAssignments,
)
from core.domain.admin.schools import require_school
from crud.database_schema import Account, AuthSession, Chairs, Delegates, School
from schemas.response_models import HashEntry, HashListResponse


def _display_name(school_name: str, key: str) -> str:
    """Turn a submitted key ("1") into the dashboard's label ("Lincoln High - #1")."""
    return f"{school_name} - #{key}"


def revoke_sessions(db: Session, account_id: int) -> None:
    """Delete every live token for an account.

    Deleting the account would cascade to `sessions` anyway, but a *reissued* hash must also
    kill the old sessions even though the account row survives.
    """
    db.execute(delete(AuthSession).where(AuthSession.account_id == account_id))


def _committee_and_country(assignment: list[str]) -> tuple[str, str]:
    """Committee and country from one submitted row, stripped.

    Rows arrive as `[committee, country]`. The older CLI shape,
    `[committee, committeeType, country]`, is still accepted so existing callers keep
    working, and its middle value is dropped: a committee's type is a property of the
    committee row (`committees.committee_type`), never of the delegate, and `delegates`
    has no column for it.
    """
    committee, country = assignment[0], assignment[-1]
    return committee.strip(), country.strip()


def mint_delegate_hashes(
    db: Session,
    *,
    school_name: str,
    assignments: dict[str, list[str]],
    actor: str,
) -> HashListResponse:
    """Register new delegates for a school and return the hash minted for each one.

    `assignments` keys are per-school display labels ("1", "2") and each value is positional:
    `[committee, country]`. The legacy three-item shape with a committee type in the middle
    is still accepted and that item is ignored - see `_committee_and_country`.

    Two rows describing the same delegation (partners) end up sharing one hash, and a
    (committee, country) pair that already has an account is refused: "regenerate" is the
    intended way to reissue. The committee must already exist - a delegate cannot be minted
    into a committee that is only a typo.
    """
    if not assignments:
        raise NoAssignments()

    for key, assignment in assignments.items():
        if len(assignment) not in (2, 3):
            raise BadAssignmentShape(key)

    school = require_school(db, school_name)

    # (committee, country) -> account minted in *this* request, so partners share a hash.
    shared: dict[tuple[str, str], Account] = {}
    hashes: list[HashEntry] = []

    for key, assignment in assignments.items():
        committee, country = _committee_and_country(assignment)
        if not committee or not country:
            raise BadAssignmentValue(key)

        pair = (committee, country)
        account = shared.get(pair)

        if account is None:
            existing = db.scalars(
                select(Delegates).where(
                    Delegates.committee == committee, Delegates.country == country
                )
            ).first()
            if existing is not None:
                raise DelegationAlreadyHasHash(country, committee)

            require_committee(db, committee)
            account = Account(
                identifier=onboarding.mint_hash(),
                role="delegate",
                name=_display_name(school_name, key),
            )
            db.add(account)
            db.flush()  # populates account.id for the profile row below
            db.add(
                Delegates(
                    account_id=account.id,
                    country=country,
                    committee=committee,
                    school_id=school.account_id,
                )
            )
            shared[pair] = account

        hashes.append(
            HashEntry(name=_display_name(school_name, key), hash=account.identifier)
        )

    db.commit()

    core.audit.technical(
        "hash.minted",
        actor=actor,
        school=school_name,
        count=len(hashes),
    )

    return HashListResponse(hashes=hashes)


def reissue_delegate_hash(
    db: Session, *, committee: str, country: str, actor: str
) -> HashEntry:
    """Mint a fresh hash for one delegate, identified by committee + country.

    Double delegation partners share the same hash, so the database does not need to track
    which delegate is which; the frontend shows the same hash for both partners.

    The new hash replaces `Account.identifier`, so the previous value can no longer log in,
    and the delegate's live sessions are revoked.
    """
    delegate = db.scalars(
        select(Delegates).where(
            Delegates.committee == committee, Delegates.country == country
        )
    ).first()
    if delegate is None:
        raise DelegateAssignmentNotFound(country, committee)

    account = db.get(Account, delegate.account_id)
    if account is None:
        # Profile row with no account: nothing to reissue, and nothing can log in.
        raise DelegateAccountMissing(country, committee)

    revoke_sessions(db, account.id)
    new_hash = onboarding.mint_hash()
    account.identifier = new_hash
    db.commit()

    core.audit.technical(
        "hash.reissued",
        actor=actor,
        delegate=f"{country} ({committee})",
        hash=core.audit.masked(new_hash),
    )

    return HashEntry(name=f"{country} ({committee})", hash=new_hash)


def reissue_chair_hash(db: Session, *, account_id: int, actor: str) -> HashEntry:
    """Mint a fresh hash for one chair, identified by account id.

    Chairs have no committee+country pair to identify them by, so the account id is the key.
    The old hash stops working and the chair's live sessions are revoked.
    """
    chair = db.get(Chairs, account_id)
    if chair is None:
        raise ChairNotFound()

    account = db.get(Account, account_id)
    if account is None:
        raise AccountMissing()

    revoke_sessions(db, account.id)
    account.identifier = onboarding.mint_hash()
    db.commit()

    core.audit.technical(
        "hash.reissued",
        actor=actor,
        role="chair",
        account=account.id,
        committee=chair.committee_name,
    )

    return HashEntry(name=chair.name, hash=account.identifier)


def list_hashes(db: Session, *, school_name: str | None = None) -> HashListResponse:
    """Delegate hashes, optionally narrowed to one school.

    Admin-only, so unlike /advisor/delegates there is nothing to mask: the real hashes come
    back. An unknown `school_name` simply matches nothing.
    """
    stmt = (
        select(Account)
        .join(Delegates, Delegates.account_id == Account.id)
        .where(Account.role == "delegate")
        .order_by(Account.name)
    )
    if school_name:
        stmt = stmt.join(School, School.account_id == Delegates.school_id).where(
            School.school_name == school_name
        )

    accounts = db.scalars(stmt).all()
    return HashListResponse(
        hashes=[HashEntry(name=account.name, hash=account.identifier) for account in accounts]
    )
