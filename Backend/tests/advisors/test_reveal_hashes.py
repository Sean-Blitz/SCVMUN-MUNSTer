"""Domain tests for ``core.domain.advisors.reveal_hashes``.

This is the backend's one credential-reveal path, so the rules are worth stating precisely:

* the password is checked **before** the school, so a wrong password never reveals whether
  the account has a school;
* ``AccountMissing`` is reachable only here - through HTTP the token has already proved the
  account exists, so this branch cannot be exercised by an endpoint test at all;
* a rejected attempt writes no audit line, while a successful one records the actor, the
  school and the count.
"""

import pytest

import core.audit
import core.security
from core.domain import advisors as domain
from core.domain.errors import AccountMissing, PasswordRejected, SchoolNotFound

PASSWORD = "Advisor!2026"


def _advisor_with_password(factory, *, identifier="ADV-PW", school_name="Password High School"):
    """An advisor account that can pass the reveal, plus its school."""
    account = factory.account(
        role="advisor",
        name="Password Advisor",
        identifier=identifier,
        password_hash=core.security.hash_password(PASSWORD),
    )
    school = factory.school(account, name=school_name)
    return account, school


def test_an_account_that_does_not_exist_raises_account_missing(db):
    """Unreachable over HTTP, and that is the point.

    The bearer token has already resolved to a real account before a route runs, so a
    session row pointing at a deleted account is the only way to get here in production.
    The endpoint maps it back to 401 so the client logs out.
    """
    with pytest.raises(AccountMissing):
        domain.reveal_hashes(db, 999_999, password="anything", actor="advisor:x")


def test_a_wrong_password_raises_password_rejected(db, factory):
    """A rejected password is a domain failure of the *reveal*, not of the session."""
    advisor, _ = _advisor_with_password(factory, identifier="ADV-WRONG")

    with pytest.raises(PasswordRejected):
        domain.reveal_hashes(db, advisor.id, password="not-the-password", actor="advisor:x")


def test_an_unclaimed_account_cannot_reveal(db, advisor):
    """A NULL password hash verifies against nothing, so nothing can be revealed.

    The default ``advisor`` fixture has no password, which is exactly the state of an admin
    who issued a hash but whose advisor has not registered yet.
    """
    with pytest.raises(PasswordRejected):
        domain.reveal_hashes(db, advisor.id, password="", actor="advisor:x")


def test_an_empty_password_is_rejected(db, factory):
    """Empty is a wrong password, not a bypass for an account that has one."""
    advisor, _ = _advisor_with_password(factory, identifier="ADV-EMPTY")

    with pytest.raises(PasswordRejected):
        domain.reveal_hashes(db, advisor.id, password="", actor="advisor:x")


def test_the_right_password_returns_the_real_hashes(db, factory, committee):
    """The same roster, with the substitute replaced by the stored identifier."""
    advisor, school = _advisor_with_password(factory, identifier="ADV-RIGHT")
    factory.delegate(
        factory.account(role="delegate", identifier="REVEAL-ME-1"),
        committee=committee,
        school=school,
    )

    revealed = domain.reveal_hashes(db, advisor.id, password=PASSWORD, actor="advisor:x")

    assert [entry.hash for entry in revealed.delegates] == ["REVEAL-ME-1"]


def test_the_reveal_is_scoped_to_the_callers_school(db, factory, committee):
    """A second school's delegates are not in the payload at all."""
    advisor, school = _advisor_with_password(
        factory, identifier="ADV-SCOPE", school_name="Scope High School"
    )
    factory.delegate(
        factory.account(role="delegate", identifier="MINE-1"),
        committee=committee,
        school=school,
    )
    rival = factory.account(role="advisor", identifier="ADV-RIVAL")
    rival_school = factory.school(rival, name="Rival High School")
    factory.delegate(
        factory.account(role="delegate", identifier="THEIRS-1"),
        committee=committee,
        school=rival_school,
    )

    revealed = domain.reveal_hashes(db, advisor.id, password=PASSWORD, actor="advisor:x")

    assert [entry.hash for entry in revealed.delegates] == ["MINE-1"]


def test_the_reveal_and_the_masked_list_agree_on_the_roster(db, factory, committee):
    """Only the hashes differ: same rows, same order, same total.

    Both payloads are built by the same private helper with a flag, but the modal and the
    page behind it must never disagree about *which* delegates exist.
    """
    advisor, school = _advisor_with_password(
        factory, identifier="ADV-COMPARE", school_name="Compare High School"
    )
    for country in ("Argentina", "France"):
        factory.delegate(
            factory.account(role="delegate"),
            committee=committee,
            school=school,
            country=country,
        )

    masked = domain.list_delegates(db, advisor.id)
    revealed = domain.reveal_hashes(db, advisor.id, password=PASSWORD, actor="advisor:x")

    assert [entry.id for entry in masked.delegates] == [
        entry.id for entry in revealed.delegates
    ]
    assert [entry.country for entry in masked.delegates] == [
        entry.country for entry in revealed.delegates
    ]
    assert masked.total == revealed.total
    assert all(entry.hash == domain.MASKED_HASH for entry in masked.delegates)
    assert all(entry.hash != domain.MASKED_HASH for entry in revealed.delegates)


def test_a_successful_reveal_is_audited_with_actor_school_and_count(
    db, factory, committee
):
    """Handing over real access codes is a credential event and says who asked.

    The school name is unique to this test because the audit file accumulates for the whole
    session - asserting on ``hashes.revealed`` alone would pass on another test's line.
    """
    advisor, school = _advisor_with_password(
        factory, identifier="ADV-AUDIT", school_name="Audit Domain High"
    )
    for identifier in ("AUD-1", "AUD-2"):
        factory.delegate(
            factory.account(role="delegate", identifier=identifier),
            committee=committee,
            school=school,
        )

    domain.reveal_hashes(db, advisor.id, password=PASSWORD, actor="advisor:42")

    line = core.audit.read("technical")
    assert 'school="Audit Domain High"' in line
    assert "actor=advisor:42" in line
    assert "count=2" in line


def test_a_rejected_reveal_writes_no_audit_line(db, factory):
    """A failed attempt is not a credential event; only a successful release is.

    The log is read before and after and the difference is compared, because earlier tests
    in the session have already written ``hashes.revealed`` lines of their own.
    """
    advisor, _ = _advisor_with_password(factory, identifier="ADV-NOAUDIT")
    before = core.audit.read("technical")

    with pytest.raises(PasswordRejected):
        domain.reveal_hashes(db, advisor.id, password="wrong", actor="advisor:x")

    assert "hashes.revealed" not in core.audit.read("technical")[len(before):]


def test_the_password_is_checked_before_the_school(db, factory):
    """A wrong password on an advisor with no school reports the password, not the school.

    That ordering is deliberate: the school is only resolved once the caller has proved they
    are the advisor, so a failure never discloses which of the two is missing.
    """
    account = factory.account(
        role="advisor",
        identifier="ADV-PW-NOSCHOOL",
        password_hash=core.security.hash_password(PASSWORD),
    )

    with pytest.raises(PasswordRejected):
        domain.reveal_hashes(db, account.id, password="wrong", actor="advisor:x")


def test_a_correct_password_on_an_advisor_without_a_school_raises_school_not_found(
    db, factory
):
    """With the password proved, the missing school is what is left to report."""
    account = factory.account(
        role="advisor",
        identifier="ADV-PW-NOSCHOOL-2",
        password_hash=core.security.hash_password(PASSWORD),
    )

    with pytest.raises(SchoolNotFound):
        domain.reveal_hashes(db, account.id, password=PASSWORD, actor="advisor:x")
