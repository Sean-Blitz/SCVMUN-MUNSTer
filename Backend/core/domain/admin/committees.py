"""Admin use cases for committees (§8.10): the list, one committee, its chairs, its delegates.

A committee's *name* is its primary key, and `delegates.committee`, `chairs.committee_name`
and `broadcasts.committee_name` all reference it without a cascade-on-update. Renaming is
therefore a domain operation rather than a column write: insert the new row, repoint all
three children, then remove the old row - one transaction, so a failure anywhere leaves the
old name and its children intact.

Same three rules as the other domain modules: no FastAPI/Starlette/`API.*` imports, ids and
data in and out, `core.domain.errors` for failures. Chairs and delegates are created with
`password_hash` NULL: they claim their hash through "First-Time Register", exactly as an
advisor does.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import core.audit
import core.storage
import crud.onboarding as onboarding
from core.domain import papers
from core.domain.errors import (
    AccountMissing,
    BlankField,
    ChairNotInCommittee,
    CommitteeExists,
    DelegateNotInCommittee,
    NoChanges,
    UnknownCommittee,
)
from crud.database_schema import Account, Broadcast, Chairs, Committees, Delegates, School, Uploads
from schemas.response_models import (
    CommitteeChairEntry,
    CommitteeDelegateEntry,
    CommitteeDetailResponse,
    DelegateRemovedResponse,
)


def require_committee(db: Session, committee_name: str) -> Committees:
    """A committee by name, or a domain error naming the fix.

    Committees are never created on the fly. This used to insert the row, so a typo silently
    produced a committee with no chair, no topic and no way to notice.
    """
    committee = db.get(Committees, committee_name)
    if committee is None:
        raise UnknownCommittee(committee_name)
    return committee


def _committee_chairs(db: Session, committee_name: str) -> list[CommitteeChairEntry]:
    rows = db.execute(
        select(Chairs, Account)
        .join(Account, Account.id == Chairs.account_id)
        .where(Chairs.committee_name == committee_name)
        .order_by(Chairs.name)
    ).all()
    return [
        CommitteeChairEntry(
            account_id=chair.account_id,
            name=chair.name,
            email=chair.email,
            hash=account.identifier,
        )
        for chair, account in rows
    ]


def _committee_delegates(db: Session, committee_name: str) -> list[CommitteeDelegateEntry]:
    """Delegates in the committee, with their school: a committee spans several schools."""
    rows = db.execute(
        select(Delegates, Account, School)
        .join(Account, Account.id == Delegates.account_id)
        .join(School, School.account_id == Delegates.school_id)
        .where(Delegates.committee == committee_name)
        .order_by(School.school_name, Delegates.country)
    ).all()
    return [
        CommitteeDelegateEntry(
            account_id=delegate.account_id,
            name=account.name,
            country=delegate.country,
            school_name=school.school_name,
            hash=account.identifier,
            paper_status=delegate.paper_status,
            paper_grade=delegate.paper_grade,
            has_paper=papers.has_file(db, delegate.account_id),
        )
        for delegate, account, school in rows
    ]


def committee_detail(db: Session, committee: Committees) -> CommitteeDetailResponse:
    """One committee's row plus its chairs and delegates, ready for the detail view."""
    return CommitteeDetailResponse(
        committee_name=committee.committee_name,
        committee_type=committee.committee_type,
        topic=committee.topic,
        chairs=_committee_chairs(db, committee.committee_name),
        delegates=_committee_delegates(db, committee.committee_name),
    )


def list_committees(db: Session) -> list[str]:
    """Committee names, for the broadcast target picker (and any future picker)."""
    return list(
        db.scalars(select(Committees.committee_name).order_by(Committees.committee_name)).all()
    )


def get_committee_detail(db: Session, committee_name: str) -> CommitteeDetailResponse:
    """One committee: its type and topic, its chairs with their hashes, and its delegates."""
    return committee_detail(db, require_committee(db, committee_name))


def create_committee(
    db: Session, *, name: str, committee_type: str | None, topic: str | None, actor: str
) -> CommitteeDetailResponse:
    """Create a committee. Its name is the primary key, so a duplicate is a conflict."""
    name = name.strip()
    if not name:
        raise BlankField("committee_name")

    if db.get(Committees, name) is not None:
        raise CommitteeExists(name)

    committee = Committees(
        committee_name=name,
        committee_type=(committee_type or "").strip() or None,
        topic=(topic or "").strip() or None,
    )
    db.add(committee)
    db.commit()

    core.audit.technical("committee.created", actor=actor, committee=name)
    return committee_detail(db, committee)


def update_committee(
    db: Session, committee_name: str, *, changes: dict, actor: str
) -> CommitteeDetailResponse:
    """Rename a committee and/or edit its type and topic.

    The rename inserts the new row, repoints `delegates`, `chairs` and `broadcasts`, then
    removes the old row - one transaction, so a failure anywhere leaves everything as it was.
    """
    committee = require_committee(db, committee_name)

    if not changes:
        raise NoChanges()

    new_name = committee.committee_name
    if "committee_name" in changes:
        value = (changes["committee_name"] or "").strip()
        if not value:
            raise BlankField("committee_name")
        new_name = value

    for field in ("committee_type", "topic"):
        if field in changes and changes[field] is not None:
            changes[field] = changes[field].strip() or None

    old_name = committee.committee_name
    renaming = new_name != old_name

    if renaming:
        if db.get(Committees, new_name) is not None:
            raise CommitteeExists(new_name)

        db.add(
            Committees(
                committee_name=new_name,
                committee_type=changes.get("committee_type", committee.committee_type),
                topic=changes.get("topic", committee.topic),
            )
        )
        db.flush()  # the children's new FK value must exist before they are repointed

        db.execute(
            update(Delegates)
            .where(Delegates.committee == old_name)
            .values(committee=new_name)
        )
        db.execute(
            update(Chairs)
            .where(Chairs.committee_name == old_name)
            .values(committee_name=new_name)
        )
        db.execute(
            update(Broadcast)
            .where(Broadcast.committee_name == old_name)
            .values(committee_name=new_name)
        )

        # Core delete on purpose: db.delete(committee) would honour the ORM's
        # "all, delete-orphan" relationships and take the delegates and chairs with it.
        db.execute(delete(Committees).where(Committees.committee_name == old_name))
        # Drop the stale instance so a later lookup cannot resurrect the old name from the
        # identity map.
        db.expunge(committee)
    else:
        if "committee_type" in changes:
            committee.committee_type = changes["committee_type"]
        if "topic" in changes:
            committee.topic = changes["topic"]

    db.commit()

    core.audit.technical(
        "committee.updated",
        actor=actor,
        committee=new_name,
        renamed_from=old_name if renaming else "-",
        fields=",".join(sorted(changes)),
    )

    return committee_detail(db, require_committee(db, new_name))


def create_committee_chair(
    db: Session, committee_name: str, *, name: str, email: str, actor: str
) -> CommitteeChairEntry:
    """Add a chair to a committee and issue their login hash."""
    committee = require_committee(db, committee_name)

    name = name.strip()
    email = email.strip()
    if not name:
        raise BlankField("name")
    if not email:
        raise BlankField("email")

    account = Account(identifier=onboarding.mint_hash(), role="chair", name=name)
    db.add(account)
    db.flush()  # the chair row uses the account id as its primary key

    chair = Chairs(
        account_id=account.id,
        name=name,
        committee_name=committee.committee_name,
        email=email,
    )
    db.add(chair)
    db.commit()

    core.audit.technical(
        "chair.created",
        actor=actor,
        account=account.id,
        committee=committee.committee_name,
    )

    return CommitteeChairEntry(
        account_id=account.id, name=name, email=email, hash=account.identifier
    )


def update_committee_chair(
    db: Session, committee_name: str, account_id: int, *, changes: dict, actor: str
) -> CommitteeChairEntry:
    """Edit a chair's name or email. The path's committee must own the chair."""
    chair = db.get(Chairs, account_id)
    if chair is None or chair.committee_name != committee_name:
        raise ChairNotInCommittee()
    account = db.get(Account, account_id)
    if account is None:
        raise AccountMissing()

    if not changes:
        raise NoChanges()

    for field in ("name", "email"):
        if field in changes:
            value = (changes[field] or "").strip()
            if not value:
                raise BlankField(field)
            setattr(chair, field, value)

    # The account's name is what the login response calls the user, so keep it in step.
    account.name = chair.name
    db.commit()

    core.audit.technical(
        "chair.updated",
        actor=actor,
        account=account_id,
        committee=committee_name,
        fields=",".join(sorted(changes)),
    )

    return CommitteeChairEntry(
        account_id=chair.account_id,
        name=chair.name,
        email=chair.email,
        hash=account.identifier,
    )


def delete_committee_chair(
    db: Session, committee_name: str, account_id: int, *, actor: str
) -> None:
    """Remove a chair: the profile row and the account, which cascades their sessions."""
    chair = db.get(Chairs, account_id)
    if chair is None or chair.committee_name != committee_name:
        raise ChairNotInCommittee()

    account = db.get(Account, account_id)
    db.delete(chair)
    db.flush()  # the profile row must go before the account it belongs to
    if account is not None:
        db.delete(account)
    db.commit()

    core.audit.technical(
        "chair.deleted",
        actor=actor,
        account=account_id,
        committee=committee_name,
    )


def delete_committee_delegate(
    db: Session, committee_name: str, account_id: int, *, actor: str
) -> DelegateRemovedResponse:
    """Remove one delegate from a committee: their rows, their hash and their stored paper.

    The path's committee must own the delegate, so a wrong committee cannot remove someone
    else's delegate. Files are unlinked after the commit because the cascade removes rows,
    not bytes - the same ordering as removing a whole school.
    """
    delegate = db.get(Delegates, account_id)
    if delegate is None or delegate.committee != committee_name:
        raise DelegateNotInCommittee()
    account = db.get(Account, account_id)

    country = delegate.country
    school_name = (
        db.scalar(select(School.school_name).where(School.account_id == delegate.school_id)) or ""
    )
    files = list(
        db.scalars(select(Uploads.file_path).where(Uploads.delegate_id == account_id)).all()
    )

    db.delete(delegate)
    db.flush()  # the delegate row must go before the account it belongs to
    if account is not None:
        db.delete(account)
    db.commit()

    for path in files:
        core.storage.delete_paper(path)

    core.audit.technical(
        "delegate.deleted",
        actor=actor,
        account=account_id,
        committee=committee_name,
        school=school_name,
        files=len(files),
    )

    return DelegateRemovedResponse(
        delegate=country, school=school_name, files_deleted=len(files)
    )
