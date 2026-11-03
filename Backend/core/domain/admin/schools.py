"""Admin use cases for schools (§8.7, §8.9): create, list, detail, edit, delete.

A school cannot exist without an advisor - `schools.account_id` *is* the advisor's account
id - so creating one creates both, with `password_hash` NULL: the advisor claims the hash
through "First-Time Register", exactly as a delegate does. Delegates come afterwards, from
POST /admin/hashes.

Same three rules as the other domain modules: no FastAPI/Starlette/`API.*` imports, ids and
data in and out, `core.domain.errors` for failures.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.audit
import core.storage
import crud.onboarding as onboarding
from core.domain import papers
from core.domain.admin.committees import require_committee
from core.domain.errors import (
    AccountMissing,
    BlankField,
    ConfirmationMismatch,
    DelegateLabelsTooLong,
    DelegateNotInSchool,
    DelegatePairTaken,
    InvalidPaymentStatus,
    MissingSchoolFields,
    NoChanges,
    SchoolExists,
    UnknownSchool,
    UnknownSchoolId,
)
from crud.database_schema import Account, Delegates, School, Uploads
from schemas.response_models import (
    SchoolDelegateEntry,
    SchoolDeletedResponse,
    SchoolDetailResponse,
    SchoolDetails,
    SchoolEntry,
    SchoolListResponse,
)

# The columns the detail editor may change. A rename is handled separately because it also
# rewrites labels; everything else is a straight column write.
SCHOOL_TEXT_FIELDS = (
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


def require_school(db: Session, school_name: str) -> School:
    """A school by name, or a domain error the admin can act on."""
    school = db.scalars(select(School).where(School.school_name == school_name)).first()
    if school is None:
        raise UnknownSchool(school_name)
    return school


def require_school_by_id(db: Session, school_id: int) -> School:
    """A school by account id (the primary key), or a domain error.

    Separate from `require_school` because the admin views address schools by id while the
    hash tooling addresses them by name; both are real keys in different places.
    """
    school = db.get(School, school_id)
    if school is None:
        raise UnknownSchoolId(school_id)
    return school


def _school_details(school: School) -> SchoolDetails:
    """The school row as the detail view edits it."""
    return SchoolDetails(
        school_name=school.school_name,
        school_address=school.school_address,
        city=school.city,
        state=school.state,
        zip_code=school.zip_code,
        advisor_name=school.advisor_name,
        advisor_phone=school.advisor_phone,
        advisor_email=school.advisor_email,
        head_delegate_name=school.head_delegate_name,
        head_delegate_email=school.head_delegate_email,
        head_delegate_phone=school.head_delegate_phone,
        payment_status=school.payment_status,
        invoiceURL=school.invoiceURL,
    )


def _delegate_entry(delegate: Delegates, account: Account, has_paper: bool) -> SchoolDelegateEntry:
    return SchoolDelegateEntry(
        account_id=delegate.account_id,
        name=account.name,
        country=delegate.country,
        committee=delegate.committee,
        hash=account.identifier,
        paper_status=delegate.paper_status,
        paper_grade=delegate.paper_grade,
        has_paper=has_paper,
    )


def _school_delegate_rows(db: Session, school_id: int):
    """(Delegates, Account) pairs for one school, in committee/country order."""
    return db.execute(
        select(Delegates, Account)
        .join(Account, Account.id == Delegates.account_id)
        .where(Delegates.school_id == school_id)
        .order_by(Delegates.committee, Delegates.country)
    ).all()


def school_detail(db: Session, school: School) -> SchoolDetailResponse:
    """One school's row, its advisor hash and each delegate, ready for the detail view."""
    advisor = db.get(Account, school.account_id)
    return SchoolDetailResponse(
        id=school.account_id,
        advisor_hash=advisor.identifier if advisor is not None else None,
        school=_school_details(school),
        delegates=[
            _delegate_entry(delegate, account, papers.has_file(db, delegate.account_id))
            for delegate, account in _school_delegate_rows(db, school.account_id)
        ],
    )


def list_schools(db: Session) -> SchoolListResponse:
    """Every school, with its advisor's hash, for the progress picker and the hash tooling.

    The advisor hash is included so a code that was misplaced can be read back without a
    database query; admin-only, and the same exposure as GET /admin/hashes for delegates.
    """
    rows = db.execute(
        select(School, Account.identifier)
        .join(Account, Account.id == School.account_id)
        .order_by(School.school_name)
    ).all()
    return SchoolListResponse(
        schools=[
            SchoolEntry(id=school.account_id, name=school.school_name, advisor_hash=identifier)
            for school, identifier in rows
        ]
    )


def create_school(db: Session, *, values: dict, actor: str) -> SchoolEntry:
    """Create a school and issue its advisor's login hash.

    The hash is returned because this is the only moment the admin is guaranteed to see it.
    """
    missing = onboarding.missing_fields(values)
    if missing:
        raise MissingSchoolFields(tuple(missing))

    if values["payment_status"] not in onboarding.PAYMENT_STATUSES:
        raise InvalidPaymentStatus(tuple(onboarding.PAYMENT_STATUSES))

    school_name = values["school_name"].strip()
    if require_exists(db, school_name):
        # Not a hash-reissue: keeping the same school_name is what ties its delegates'
        # papers, progress ticks and invoices together, so a duplicate is a mistake to
        # surface, not something to merge.
        raise SchoolExists(school_name)

    advisor, _school = onboarding.create_school_with_advisor(db, values=values)
    db.commit()

    core.audit.technical(
        "school.created",
        actor=actor,
        school=school_name,
        advisor=advisor.id,
    )

    return SchoolEntry(id=advisor.id, name=school_name, advisor_hash=advisor.identifier)


def require_exists(db: Session, school_name: str) -> bool:
    """True when a school already uses that name."""
    return (
        db.scalars(select(School).where(School.school_name == school_name)).first() is not None
    )


def get_school_detail(db: Session, school_id: int) -> SchoolDetailResponse:
    """One school: every editable detail, the advisor's hash, and each delegate."""
    return school_detail(db, require_school_by_id(db, school_id))


def update_school(db: Session, school_id: int, *, changes: dict, actor: str) -> SchoolDetailResponse:
    """Apply the fields present in `changes`; leave the rest alone.

    Renaming is the one behaviour with a side effect: delegate labels are stored as
    "<school> - #<key>" in `accounts.name`, so the rename rewrites the ones that still carry
    the old prefix, or the hash lists would keep showing a school that no longer exists.
    """
    school = require_school_by_id(db, school_id)

    if not changes:
        raise NoChanges()

    for field in SCHOOL_TEXT_FIELDS:
        if field in changes:
            value = (changes[field] or "").strip()
            if not value:
                raise BlankField(field)
            changes[field] = value

    if (
        "payment_status" in changes
        and changes["payment_status"] not in onboarding.PAYMENT_STATUSES
    ):
        raise InvalidPaymentStatus(tuple(onboarding.PAYMENT_STATUSES))

    if "invoiceURL" in changes and changes["invoiceURL"] is not None:
        changes["invoiceURL"] = changes["invoiceURL"].strip() or None

    old_name = school.school_name
    new_name = changes.get("school_name", old_name)
    renaming = new_name != old_name
    rows = _school_delegate_rows(db, school.account_id) if renaming else []

    if renaming:
        clash = db.scalars(
            select(School).where(
                School.school_name == new_name, School.account_id != school.account_id
            )
        ).first()
        if clash is not None:
            raise SchoolExists(new_name)

        # The label column is 100 characters; refuse rather than let Postgres truncate-fail.
        old_prefix = f"{old_name} - #"
        too_long = [
            account.name
            for _delegate, account in rows
            if account.name.startswith(old_prefix)
            and len(f"{new_name} - #{account.name[len(old_prefix):]}") > 100
        ]
        if too_long:
            raise DelegateLabelsTooLong()

    for field, value in changes.items():
        setattr(school, field, value)

    if renaming:
        old_prefix = f"{old_name} - #"
        for _delegate, account in rows:
            if account.name.startswith(old_prefix):
                account.name = f"{new_name} - #{account.name[len(old_prefix):]}"

    db.commit()

    core.audit.technical(
        "school.updated",
        actor=actor,
        school=new_name,
        fields=",".join(sorted(changes)),
    )

    return school_detail(db, school)


def update_school_delegate(
    db: Session, school_id: int, account_id: int, *, changes: dict, actor: str
) -> SchoolDelegateEntry:
    """Move one delegate to a different country or committee.

    The school id in the path must own the delegate, so a wrong id cannot be used to edit
    another school's delegate. Country and committee are the only writable fields; the hash
    is reissued through POST /admin/hashes/regenerate/delegate instead of being typed.
    """
    delegate = db.get(Delegates, account_id)
    if delegate is None or delegate.school_id != school_id:
        raise DelegateNotInSchool()
    account = db.get(Account, account_id)
    if account is None:
        raise AccountMissing()

    if not changes:
        raise NoChanges()

    country, committee = delegate.country, delegate.committee
    for field in ("country", "committee"):
        if field in changes:
            value = (changes[field] or "").strip()
            if not value:
                raise BlankField(field)
            if field == "country":
                country = value
            else:
                committee = value

    if (country, committee) != (delegate.country, delegate.committee):
        # There is no unique constraint on the pair, so the rule that a delegation has one
        # hash lives here, mirroring create_delegate_hashes.
        clash = db.scalars(
            select(Delegates).where(
                Delegates.committee == committee,
                Delegates.country == country,
                Delegates.account_id != account_id,
            )
        ).first()
        if clash is not None:
            raise DelegatePairTaken(country, committee)

        if committee != delegate.committee:
            # The committee list is authoritative: a typo must not create a phantom.
            require_committee(db, committee)

        delegate.country = country
        delegate.committee = committee
        db.commit()

        core.audit.technical(
            "delegate.updated",
            actor=actor,
            account=account_id,
            school=school_id,
            fields=",".join(sorted(changes)),
        )

    return _delegate_entry(delegate, account, papers.has_file(db, account_id))


def delete_school(
    db: Session, school_id: int, *, confirm: str, actor: str
) -> SchoolDeletedResponse:
    """Delete a school, its advisors and its delegates, and unlink their stored papers.

    `confirm` must repeat the school's name: the confirmation dialog lives in the browser, so
    the server checks intent itself rather than trusting that the UI asked.

    Order matters. `delegates.school_id -> schools` is NO ACTION, so the delegates have to go
    before the advisor account whose deletion cascades the school away. Papers are rows
    deleted by the ORM cascade but files unlinked here, because a cascade only removes rows.
    """
    school = require_school_by_id(db, school_id)

    if confirm.strip() != school.school_name:
        raise ConfirmationMismatch()

    name = school.school_name
    rows = _school_delegate_rows(db, school.account_id)

    files: list[str] = []
    for delegate, account in rows:
        files.extend(
            db.scalars(
                select(Uploads.file_path).where(Uploads.delegate_id == account.id)
            ).all()
        )
        db.delete(delegate)
        db.flush()  # the delegate row must go before the account it belongs to
        db.delete(account)

    db.commit()

    # Best-effort: the rows are gone, so a file that cannot be removed is only wasted disk.
    for path in files:
        core.storage.delete_paper(path)

    advisor = db.get(Account, school.account_id)
    if advisor is not None:
        db.delete(advisor)  # cascades the schools row
        db.commit()

    core.audit.technical(
        "school.deleted",
        actor=actor,
        school=name,
        delegates=len(rows),
        files=len(files),
    )

    return SchoolDeletedResponse(
        school=name, delegates_deleted=len(rows), files_deleted=len(files)
    )
