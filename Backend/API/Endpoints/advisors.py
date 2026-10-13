"""
Advisor endpoints (/advisor/*) — Frontend-API-Contract.md §3 and §4.

An advisor is scoped to one school, so every route resolves the school from the
calling user rather than accepting a school identifier from the client.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from API.dependencies import CurrentUser, get_current_user, require_roles
import core.security
import core.storage
from crud.database_schema import Account, Delegates, School, Uploads
from crud.db import get_db
from schemas.request_models import VerifyHashesRequest
from schemas.response_models import (
    AdvisorDelegate,
    AdvisorDelegatesResponse,
    AdvisorSchoolResponse,
    BillingInfo,
    ChecklistItem,
    SchoolInfo,
)

router = APIRouter(
    prefix="/advisor",
    tags=["advisor"],
    dependencies=[Depends(require_roles("advisor"))],
)

# What /delegates returns in place of a real hash. The frontend masks the value as well,
# but a hash must not reach the browser at all until /verify-hashes has been passed: the
# JSON is readable in devtools whatever the page chooses to render.
MASKED_HASH = "••••••••"


def _get_school(db: Session, account_id: int) -> School:
    """The advisor's own school, or a 404 naming what is missing."""
    school = db.scalars(select(School).where(School.account_id == account_id)).first()
    if school is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No school is attached to this account.",
        )
    return school


def _delegates_for_school(
    db: Session, school: School, *, reveal_hashes: bool
) -> AdvisorDelegatesResponse:
    """Build the §3.1 payload for one school.

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


@router.get("/delegates", response_model=AdvisorDelegatesResponse)
def list_delegates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorDelegatesResponse:
    """
    List the advisor's delegates, resolved from the caller rather than from a query
    parameter, so one school cannot read another's roster.

    `hash` must be masked here — the real values are only released by
    /advisor/verify-hashes, which asks for the password again first.
    """
    school = _get_school(db, user.id)
    return _delegates_for_school(db, school, reveal_hashes=False)


@router.get("/delegates/{delegate_id}/paper")
def download_delegate_paper(
    delegate_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> Response:
    """
    Return the delegate's position paper as a PDF blob.

    `delegate_id` is looked up *within the advisor's own school*, so asking for another
    school's delegate answers 404 exactly as a non-existent one does - there is no
    "exists but forbidden" signal to probe with. The file itself is located from the
    newest `position_papers` row, never from anything the client sends.
    """
    school = _get_school(db, user.id)

    delegate = db.scalars(
        select(Delegates).where(
            Delegates.account_id == delegate_id,
            Delegates.school_id == school.account_id,
        )
    ).first()
    if delegate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such delegate in your school.",
        )

    # Uploads are append-only, so the newest row is the paper currently in force.
    upload = db.scalars(
        select(Uploads)
        .where(Uploads.delegate_id == delegate.account_id)
        .order_by(Uploads.upload_time.desc(), Uploads.upload_id.desc())
        .limit(1)
    ).first()
    if upload is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This delegate has not submitted a position paper yet.",
        )

    path = core.storage.paper_path(upload.file_path)
    if not path.is_file():
        # Row without a file: the volume was restored from an older backup, or the file
        # was removed by hand. Say so rather than letting FileResponse raise.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The stored file is missing. Ask the delegate to upload it again.",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=upload.file_name or f"delegate_{delegate_id}_paper.pdf",
    )


@router.post("/verify-hashes", response_model=AdvisorDelegatesResponse)
def verify_hashes_and_reveal(
    payload: VerifyHashesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorDelegatesResponse:
    """
    Re-authenticate the advisor and, on success, return the same delegate list with real
    (unmasked) hashes.

    A wrong password answers **403, not 401**: the frontend's axios interceptor treats
    every 401 as a dead session and would log the advisor out and redirect to the login
    page instead of showing the message inside the password modal. 401 is kept for the
    case where the token itself resolves to an account that no longer exists, where
    being sent back to the login page is the right outcome.
    """
    account = db.get(Account, user.id)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")

    # verify_password returns False for an unclaimed account (password_hash IS NULL), so a
    # school whose advisor never completed registration cannot reveal anything either -
    # and learns nothing about why from the message.
    if not core.security.verify_password(payload.password, account.password_hash):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Incorrect password. Access denied.",
        )

    school = _get_school(db, user.id)
    return _delegates_for_school(db, school, reveal_hashes=True)


def _checklist_items(school: School) -> list[ChecklistItem]:
    """Map the school's stored `check_list` JSON onto the response shape.

    The column is free-form JSONB, so anything that is not a `{label, completed}` object
    is skipped rather than turning the whole panel into a 500. A school with no list
    stores NULL and gets an empty panel.
    """
    items: list[ChecklistItem] = []
    for entry in school.check_list or []:
        if not isinstance(entry, dict) or not entry.get("label"):
            continue
        items.append(
            ChecklistItem(
                label=str(entry["label"]),
                completed=bool(entry.get("completed", False)),
            )
        )
    return items


@router.get("/school", response_model=AdvisorSchoolResponse)
def get_school_overview(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AdvisorSchoolResponse:
    """
    Return the advisor's school details, billing status, and conference checklist.

    Field names follow the frontend's §4.1 shape, which is why several are renames of the
    columns (`school_name` → `name`, `zip_code` → `zip`, `invoiceURL` → `invoiceUrl`).
    """
    school = _get_school(db, user.id)

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
        checklist=_checklist_items(school),
    )
