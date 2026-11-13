"""Domain tests for ``core.domain.admin.awards`` (§8.5) and ``passwords`` (§8.12).

**Awards report.** A read over what chairs assigned. The rules are about exclusion: ``"None"``
is the frontend's "no award" marker, and a NULL assignment means nothing decided - neither is
an award. ``"Candidate"`` is kept, because a shortlist is a decision.

**Password reset.** A hash and a password are different things on the same row, and neither
derives from the other, so "forgot my password" needs its own operation. It returns the account
to the state it was created in (``password_hash = NULL``) and revokes the sessions - never
inventing a password, so the admin still never knows one.
"""

import pytest
from sqlalchemy import select

import core.audit
import core.security
from core.domain.admin import awards, passwords
from core.domain.errors import AccountNotFound, AccountNotRegistered
from crud.database_schema import Account, AuthSession


# ---------------------------------------------------------------------------
# The award report
# ---------------------------------------------------------------------------


def test_the_report_is_empty_before_anything_is_assigned(db, factory, committee, school):
    factory.new_delegate(committee, school, country="France")

    assert awards.get_awards_overview(db).committees == []


def test_assignments_are_grouped_by_committee_in_order(db, factory, committee, school):
    unsc = factory.committee("UNSC")
    factory.new_delegate(committee, school, country="Spain", assigned_award="Best Delegate")
    factory.new_delegate(committee, school, country="France", assigned_award="Candidate")
    factory.new_delegate(unsc, school, country="Italy", assigned_award="Honorable Mention")

    result = awards.get_awards_overview(db)

    assert [(entry.committee, [(a.country, a.award) for a in entry.awards]) for entry in result.committees] == [
        (
            "DISEC",
            [("France", "Candidate"), ("Spain", "Best Delegate")],
        ),
        ("UNSC", [("Italy", "Honorable Mention")]),
    ]


def test_none_is_not_an_award(db, factory, committee, school):
    factory.new_delegate(committee, school, country="France", assigned_award="None")
    factory.new_delegate(committee, school, country="Spain", assigned_award="Candidate")

    result = awards.get_awards_overview(db)

    assert [entry.country for entry in result.committees[0].awards] == ["Spain"]


def test_an_unassigned_delegate_is_invisible(db, factory, committee, school):
    factory.new_delegate(committee, school, country="France")

    assert awards.get_awards_overview(db).committees == []


def test_a_committee_with_nothing_assigned_is_omitted(db, factory, committee, school):
    factory.new_delegate(committee, school, country="France", assigned_award="Best Delegate")
    factory.new_delegate(factory.committee("UNSC"), school, country="Italy")

    result = awards.get_awards_overview(db)

    assert [entry.committee for entry in result.committees] == ["DISEC"]


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


def test_a_reset_clears_the_password_and_returns_the_hash(db, factory):
    """The holder claims the hash again through First-Time Register with a new password."""
    account = factory.account(
        role="delegate",
        identifier="RESET-1",
        password_hash=core.security.hash_password("Str0ng!pass"),
    )

    result = passwords.reset_password(db, account_id=account.id, actor="admin:1")

    assert (result.name, result.role, result.hash) == (account.name, "delegate", "RESET-1")

    db.expire_all()
    assert account.password_hash is None
    assert account.identifier == "RESET-1"  # the code itself is untouched


def test_a_reset_revokes_the_sessions(db, factory):
    """A reset that left sessions running would not lock anyone out."""
    account = factory.account(
        role="delegate",
        password_hash=core.security.hash_password("Str0ng!pass"),
    )
    factory.headers(account)
    theirs = select(AuthSession).where(AuthSession.account_id == account.id)
    assert db.scalars(theirs).all() != []

    passwords.reset_password(db, account_id=account.id, actor="admin:1")

    assert db.scalars(theirs).all() == []


def test_another_accounts_sessions_are_untouched(db, factory):
    account = factory.account(
        role="delegate", password_hash=core.security.hash_password("Str0ng!pass")
    )
    bystander = factory.account(role="delegate", password_hash=core.security.hash_password("Other!1"))
    factory.headers(bystander)
    keep = select(AuthSession).where(AuthSession.account_id == bystander.id)

    passwords.reset_password(db, account_id=account.id, actor="admin:1")

    assert db.scalars(keep).all() != []


def test_an_unregistered_account_is_refused(db, factory):
    """There is no password to clear; reporting success would suggest something was fixed."""
    account = factory.account(role="delegate", identifier="UNCLAIMED-1")

    with pytest.raises(AccountNotRegistered) as raised:
        passwords.reset_password(db, account_id=account.id, actor="admin:1")

    assert str(account.name) in str(raised.value)


def test_an_unknown_account_carries_its_id(db):
    with pytest.raises(AccountNotFound) as raised:
        passwords.reset_password(db, account_id=999_999, actor="admin:1")

    assert raised.value.account_id == 999_999


def test_a_reset_is_audited(db, factory):
    """Who cleared whose password is a credential event."""
    account = factory.account(
        role="delegate",
        identifier="AUDITED-1",
        password_hash=core.security.hash_password("Str0ng!pass"),
    )
    before = core.audit.read("technical")

    passwords.reset_password(db, account_id=account.id, actor="admin:7")

    written = core.audit.read("technical")[len(before):]
    assert "password.reset" in written
    assert "actor=admin:7" in written
    assert f"account={account.id}" in written


def test_the_account_row_is_not_deleted(db, factory):
    """A reset is not a delete: the hash stays usable."""
    account = factory.account(
        role="delegate", identifier="KEPT-1", password_hash=core.security.hash_password("Str0ng!pass")
    )

    passwords.reset_password(db, account_id=account.id, actor="admin:1")

    assert db.get(Account, account.id) is not None
