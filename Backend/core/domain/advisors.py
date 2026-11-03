"""Advisor use cases: the school roster, paper downloads, credential reveal, school overview.

Same three rules as the other domain modules:

* nothing here imports FastAPI, Starlette or `API.*`;
* it takes the caller's `account_id` (and a delegate id where relevant) and returns data -
  response models or a `papers.PaperFile` - never a `Response`;
* failures are `core.domain.errors` exceptions, mapped by `API/Endpoints/advisors.py`.

An advisor is scoped to one school, so every function resolves the school from the account
rather than accepting a school identifier from the caller. That rule lives here because it
is the *authorization* rule, not a routing detail.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.audit
import core.security
from core.domain import papers
from core.domain.errors import (
    AccountMissing,
    DelegateNotInSchool,
    PasswordRejected,
    SchoolNotFound,
)
from crud.database_schema import (
    Account,
    ChecklistProgress,
    ConferenceChecklist,
    Delegates,
    School,
)
from schemas.response_models import (
    AdvisorDelegate,
    AdvisorDelegatesResponse,
    AdvisorSchoolResponse,
    BillingInfo,
    ChecklistItem,
    SchoolInfo,
)

# What the roster returns in place of a real hash. The frontend masks the value as well,
# but a hash must not reach the browser at all until the reveal has been passed: the JSON
# is readable in devtools whatever the page chooses to render.
MASKED_HASH = "••••••••"


def _school_for(db: Session, account_id: int) -> School:
    """The advisor's own school, or a domain error naming what is missing."""
    school = db.scalars(select(School).where(School.account_id == account_id)).first()
    if school is None:
        raise SchoolNotFound()
    return school


def _delegates_for_school(
    db: Session, school: School, *, reveal_hashes: bool
) -> AdvisorDelegatesResponse:
    """Build the roster payload for one school.

    One query joins each delegate profile to its account, because both the login hash
    (`identifier`) and the registered flag (`password_hash IS NOT NULL`, set by
    /auth/register) live on accounts rather than on the profile. Ordered by committee
    then country so the list is stable between requests.
    """
    rows = db.execute(
        select(Delegates, Account)
        .join(Account, Account.id == Delegates.account_id)
        .where(Delegates.school_id == school.account_id)
        .order_by(Delegates.committee, Delegates.country)
    ).all()

    delegates = [
        AdvisorDelegate(
            # The profile's primary key *is* the account id, which is what the
            # /delegates/{id}/paper route expects back.
            id=delegate.account_id,
            country=delegate.country,
            committee=delegate.committee,
            paperStatus=delegate.paper_status,
            paperGrade=delegate.paper_grade,
            hash=account.identifier if reveal_hashes else MASKED_HASH,
            registered=account.password_hash is not None,
        )
        for delegate, account in rows
    ]

    return AdvisorDelegatesResponse(delegates=delegates, total=len(delegates))


def list_delegates(db: Session, account_id: int) -> AdvisorDelegatesResponse:
    """The advisor's delegates with masked hashes.

    `hash` is masked here on purpose: the real values are only released by
    `reveal_hashes`, which asks for the password again first.
    """
    return _delegates_for_school(db, _school_for(db, account_id), reveal_hashes=False)


def reveal_hashes(
    db: Session, account_id: int, *, password: str, actor: str
) -> AdvisorDelegatesResponse:
    """Re-authenticate the advisor and return the roster with real hashes.

    A rejected password is a domain failure, not an authentication failure of the session:
    the caller is still signed in, they just did not prove they are the advisor again. The
    endpoint maps it to 403 for that reason (see its docstring).

    An unclaimed account cannot reveal anything: `verify_password` returns False for a NULL
    hash, and the message does not say why.
    """
    account = db.get(Account, account_id)
    if account is None:
        raise AccountMissing()

    if not core.security.verify_password(password, account.password_hash):
        raise PasswordRejected()

    school = _school_for(db, account_id)
    revealed = _delegates_for_school(db, school, reveal_hashes=True)

    # Handing over a school's real access codes is a credential event: it belongs in the
    # technical log beside the logins those codes are about to be used for.
    core.audit.technical(
        "hashes.revealed",
        actor=actor,
        school=school.school_name,
        count=revealed.total,
    )
    return revealed


def get_paper_file(db: Session, account_id: int, delegate_id: int) -> papers.PaperFile:
    """A delegate's paper, scoped to the advisor's school and resolved to bytes.

    The delegate is looked up *within the advisor's own school*, so asking for another
    school's delegate fails exactly as a non-existent one does - there is no
    "exists but forbidden" signal to probe with. The file itself comes from the newest
    `position_papers` row, never from anything the client sends.
    """
    school = _school_for(db, account_id)

    delegate = db.scalars(
        select(Delegates).where(
            Delegates.account_id == delegate_id,
            Delegates.school_id == school.account_id,
        )
    ).first()
    if delegate is None:
        raise DelegateNotInSchool()

    paper = papers.paper_in_force(db, delegate.account_id)
    return papers.PaperFile(
        path=paper.path,
        download_name=f"delegate_{delegate_id}_paper.pdf",
    )


def _checklist_items(db: Session, school: School) -> list[ChecklistItem]:
    """The shared checklist labels, each with *this* school's tick.

    Labels are conference-wide (conference_checklist); ticks are not (checklist_progress),
    so the outer join is what makes Lincoln's invoice tick invisible to Rival. A missing
    progress row is simply "not done".
    """
    rows = db.execute(
        select(ConferenceChecklist, ChecklistProgress.completed)
        .outerjoin(
            ChecklistProgress,
            (ChecklistProgress.item_id == ConferenceChecklist.id)
            & (ChecklistProgress.school_id == school.account_id),
        )
        .order_by(ConferenceChecklist.position, ConferenceChecklist.id)
    ).all()

    return [
        ChecklistItem(label=item.label, completed=bool(completed))
        for item, completed in rows
    ]


def get_school_overview(db: Session, account_id: int) -> AdvisorSchoolResponse:
    """The advisor's school details, billing status, and conference checklist.

    Field names follow the frontend's §4.1 shape, which is why several are renames of the
    columns (`school_name` → `name`, `zip_code` → `zip`, `invoiceURL` → `invoiceUrl`).
    """
    school = _school_for(db, account_id)

    return AdvisorSchoolResponse(
        school=SchoolInfo(
            name=school.school_name,
            address=school.school_address,
            city=school.city,
            state=school.state,
            zip=school.zip_code,
            advisorName=school.advisor_name,
            advisorEmail=school.advisor_email,
            advisorPhone=school.advisor_phone,
            headDelegateName=school.head_delegate_name,
            headDelegateEmail=school.head_delegate_email,
            headDelegatePhone=school.head_delegate_phone,
        ),
        billing=BillingInfo(
            invoiceUrl=school.invoiceURL or "",
            paymentStatus=school.payment_status or "unpaid",
        ),
        checklist=_checklist_items(db, school),
    )
