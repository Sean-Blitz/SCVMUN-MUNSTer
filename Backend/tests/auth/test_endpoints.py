"""API tests for /auth/* - the three routes every other route depends on.

These are the only ungated routes, which makes them the only place where a wrong status code
is felt everywhere: the frontend's axios interceptor logs out on **any 401**, so this file
pins which failures are 401 and which deliberately are not.

Three contract decisions are asserted as errors rather than as documentation:

* an unknown access code, a wrong password and an unclaimed account all return the **same 401
  body**, so the endpoint cannot be used to discover which hashes exist;
* registering an already-claimed code is **409, not 401** - a 401 would bounce the user to the
  login screen instead of telling them to log in;
* logout is **204 for every input**, including no token and a token that is already gone,
  because failing there would only make the client show an error while it is signed out.

Every other suite creates its session row directly (`factory.token`). This is the only place
where the real login path - password verification, the session row, the audit lines - runs.

Run with::

    cd Backend && .venv/bin/python -m pytest tests/auth/test_endpoints.py -v
"""

import pytest
from sqlalchemy import select

import core.audit
import core.captcha
import core.security
from crud.database_schema import AuthSession

PASSWORD = "Delegate!2026"

# The message all three login failures share. Asserted by spelling it out once.
LOGIN_FAILED_MESSAGE = (
    "Invalid access code or password. Check if you have registered yet."
)

WEAK_PASSWORD_MESSAGE = (
    "Password must be at least 8 characters long and include at least one uppercase "
    "letter, one lowercase letter, one digit, and one special character."
)


def _registered_account(factory, *, role="delegate", identifier="HASH-1", password=PASSWORD):
    """An account that has already claimed its hash."""
    return factory.account(
        role=role,
        name=f"{role.title()} Person",
        identifier=identifier,
        password_hash=core.security.hash_password(password),
    )


def _unclaimed_account(factory, *, role="delegate", identifier="HASH-NEW"):
    """An account with a pre-issued hash that nobody has registered yet."""
    return factory.account(
        role=role, name=f"{role.title()} Person", identifier=identifier, password_hash=None
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


def test_login_returns_the_user_and_a_token_that_actually_works(
    client, factory, committee, school
):
    """The token from login must authenticate a protected route.

    This is the one test that closes the loop between auth and everything else: every other
    suite mints its session row directly, so a bug that issued an unusable token would only
    show up here.
    """
    account = _registered_account(factory, role="delegate", identifier="DEL-HASH-1")
    factory.delegate(account, committee=committee, school=school)

    response = client.post(
        "/api/auth/login", json={"hash": "DEL-HASH-1", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"name": "Delegate Person", "role": "delegate"}

    protected = client.get(
        "/api/delegate/my-assignment",
        headers={"Authorization": f"Bearer {body['token']}"},
    )
    assert protected.status_code == 200


def test_login_stores_only_the_digest_of_the_token(client, db, factory):
    """The raw token exists in the response and nowhere else.

    A database leak must not hand over live sessions, so the row holds the SHA-256 digest.
    """
    account = _registered_account(factory, identifier="DEL-HASH-2")

    token = client.post(
        "/api/auth/login", json={"hash": "DEL-HASH-2", "password": PASSWORD}
    ).json()["token"]

    sessions = db.scalars(select(AuthSession)).all()
    assert len(sessions) == 1
    assert sessions[0].account_id == account.id
    assert sessions[0].token_hash == core.security.hash_token(token)
    assert sessions[0].token_hash != token


def test_login_records_the_last_login_time(client, db, factory):
    account = _registered_account(factory, identifier="DEL-HASH-3")
    assert account.last_login is None

    client.post("/api/auth/login", json={"hash": "DEL-HASH-3", "password": PASSWORD})

    db.expire_all()
    assert account.last_login is not None


def test_login_takes_the_role_from_the_account(client, factory):
    """The request carries no role at all; whatever the row says is what comes back."""
    _registered_account(factory, role="chair", identifier="CHAIR-HASH-1")

    body = client.post(
        "/api/auth/login", json={"hash": "CHAIR-HASH-1", "password": PASSWORD}
    ).json()

    assert body["user"]["role"] == "chair"


def test_login_writes_an_audit_line(client, factory):
    _registered_account(factory, identifier="DEL-HASH-4")
    before = core.audit.read("technical")

    client.post("/api/auth/login", json={"hash": "DEL-HASH-4", "password": PASSWORD})

    written = core.audit.read("technical")[len(before):]
    assert "login.ok" in written


def test_an_unknown_access_code_is_401(client):
    response = client.post(
        "/api/auth/login", json={"hash": "NEVER-ISSUED", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {"message": LOGIN_FAILED_MESSAGE}


def test_a_wrong_password_is_401(client, factory):
    _registered_account(factory, identifier="DEL-HASH-5")

    response = client.post(
        "/api/auth/login", json={"hash": "DEL-HASH-5", "password": "Wrong!2026"}
    )

    assert response.status_code == 401
    assert response.json() == {"message": LOGIN_FAILED_MESSAGE}


def test_an_unregistered_account_is_401_with_the_same_body(client, factory):
    """An unclaimed hash (password NULL) must not be distinguishable from a wrong password."""
    _unclaimed_account(factory, identifier="DEL-HASH-6")

    response = client.post(
        "/api/auth/login", json={"hash": "DEL-HASH-6", "password": "Anything!1"}
    )

    assert response.status_code == 401
    assert response.json() == {"message": LOGIN_FAILED_MESSAGE}


def test_the_three_login_failures_are_indistinguishable(client, factory):
    """Byte-identical responses: the endpoint is not an oracle for which hashes exist.

    The audit log is where the difference lives - and that is deliberate, because an admin
    debugging a delegate who "swears their password is right" needs it.
    """
    _registered_account(factory, identifier="KNOWN-HASH")
    _unclaimed_account(factory, identifier="UNCLAIMED-HASH")

    unknown = client.post(
        "/api/auth/login", json={"hash": "GHOST-HASH", "password": PASSWORD}
    )
    wrong = client.post(
        "/api/auth/login", json={"hash": "KNOWN-HASH", "password": "Wrong!2026"}
    )
    unclaimed = client.post(
        "/api/auth/login", json={"hash": "UNCLAIMED-HASH", "password": PASSWORD}
    )

    assert unknown.status_code == wrong.status_code == unclaimed.status_code == 401
    assert unknown.json() == wrong.json() == unclaimed.json()


def test_a_failed_login_is_audited_with_the_reason(client, factory):
    """The log distinguishes "unregistered" from "bad password"; the response must not."""
    _unclaimed_account(factory, identifier="DEL-HASH-7")
    before = core.audit.read("technical")

    client.post("/api/auth/login", json={"hash": "DEL-HASH-7", "password": "Anything!1"})

    written = core.audit.read("technical")[len(before):]
    assert "login.failed" in written
    assert "reason=unregistered" in written


def test_a_missing_password_is_a_422_with_a_readable_sentence(client, factory):
    _registered_account(factory, identifier="DEL-HASH-8")

    response = client.post("/api/auth/login", json={"hash": "DEL-HASH-8"})

    assert response.status_code == 422
    assert response.json() == {"message": "Password is required."}


def test_an_over_long_hash_is_a_422(client):
    """The cap keeps a hostile client from making the lookup work on megabytes."""
    response = client.post(
        "/api/auth/login", json={"hash": "x" * 101, "password": PASSWORD}
    )

    assert response.status_code == 422
    assert response.json() == {"message": "Hash must be at most 100 characters."}


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


def test_register_claims_the_hash_and_returns_a_working_session(
    client, db, factory, committee, school
):
    """Registering is what turns a pre-issued row into a usable account."""
    account = _unclaimed_account(factory, identifier="CLAIM-1")
    factory.delegate(account, committee=committee, school=school)

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-1", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"name": "Delegate Person", "role": "delegate"}

    db.expire_all()
    assert account.password_hash is not None
    assert core.security.verify_password(PASSWORD, account.password_hash)

    # ...and the token it returns logs the new account in.
    assert (
        client.get(
            "/api/delegate/my-assignment",
            headers={"Authorization": f"Bearer {body['token']}"},
        ).status_code
        == 200
    )


def test_register_takes_the_role_from_the_row(client, factory):
    """There is no role in the body; it comes from the hash the admin minted."""
    _unclaimed_account(factory, role="advisor", identifier="CLAIM-ADV")

    body = client.post(
        "/api/auth/register", json={"hash": "CLAIM-ADV", "password": PASSWORD}
    ).json()

    assert body["user"] == {"name": "Advisor Person", "role": "advisor"}


def test_register_writes_an_audit_line(client, factory):
    _unclaimed_account(factory, identifier="CLAIM-2")
    before = core.audit.read("technical")

    client.post("/api/auth/register", json={"hash": "CLAIM-2", "password": PASSWORD})

    written = core.audit.read("technical")[len(before):]
    assert "register.claimed" in written


def test_an_unknown_access_code_is_401(client):
    response = client.post(
        "/api/auth/register", json={"hash": "NEVER-ISSUED", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {
        "message": "Unknown access code. Ask your advisor for a valid hash."
    }


def test_an_already_registered_code_is_409_not_401(client, factory):
    """401 would make the axios interceptor log the user out and bounce them to the login
    screen; 409 survives to be shown inside the form."""
    _registered_account(factory, identifier="CLAIM-3")

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-3", "password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json() == {
        "message": "This access code has already been registered. Log in instead."
    }


@pytest.mark.parametrize(
    "weak",
    ["Ab1!", "abcdefg1!", "ABCDEFG1!", "Abcdefgh!", "Abcdefg1"],
    ids=["too-short", "no-uppercase", "no-lowercase", "no-digit", "no-special"],
)
def test_a_weak_password_is_400(client, factory, weak):
    """One case per rule, so a regression names the rule that was loosened."""
    _unclaimed_account(factory, identifier="CLAIM-WEAK")

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-WEAK", "password": weak}
    )

    assert response.status_code == 400
    assert response.json() == {"message": WEAK_PASSWORD_MESSAGE}


def test_a_rejected_password_does_not_claim_the_hash(client, db, factory):
    """A 400 must leave the row unclaimed, or the holder is locked out of their own code."""
    account = _unclaimed_account(factory, identifier="CLAIM-4")

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-4", "password": "weak"}
    )

    assert response.status_code == 400
    db.expire_all()
    assert account.password_hash is None


def test_an_over_long_password_is_a_422(client, factory):
    """Beats Argon2 being handed a megabyte: the model rejects it before the handler runs."""
    _unclaimed_account(factory, identifier="CLAIM-5")

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-5", "password": "A1!" + "x" * 300}
    )

    assert response.status_code == 422
    assert response.json() == {"message": "Password must be at most 200 characters."}


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


def _login(client, identifier, password=PASSWORD):
    return client.post(
        "/api/auth/login", json={"hash": identifier, "password": password}
    ).json()["token"]


def test_logout_revokes_the_presented_token(client, factory):
    _registered_account(factory, identifier="DEL-HASH-9")
    token = _login(client, "DEL-HASH-9")
    headers = {"Authorization": f"Bearer {token}"}

    logout = client.post("/api/auth/logout", headers=headers)

    assert logout.status_code == 204
    assert client.get("/api/delegate/my-assignment", headers=headers).status_code == 401


def test_logout_is_idempotent(client, factory):
    """A second call, or an already-revoked token, is still a 204 rather than an error."""
    _registered_account(factory, identifier="DEL-HASH-10")
    headers = {"Authorization": f"Bearer {_login(client, 'DEL-HASH-10')}"}

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.post("/api/auth/logout", headers=headers).status_code == 204


def test_logout_without_a_token_is_still_204(client):
    """The client may be signed out already; making that an error helps nobody."""
    assert client.post("/api/auth/logout").status_code == 204


def test_logout_leaves_other_sessions_alone(client, factory, committee, school):
    """One device signing out must not sign out the others."""
    account = _registered_account(factory, identifier="DEL-HASH-11")
    factory.delegate(account, committee=committee, school=school)
    first = _login(client, "DEL-HASH-11")
    second = _login(client, "DEL-HASH-11")

    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {first}"})

    still_valid = client.get(
        "/api/delegate/my-assignment", headers={"Authorization": f"Bearer {second}"}
    )
    assert still_valid.status_code == 200


def test_a_revocation_is_audited_but_a_no_op_logout_is_not(client, factory):
    """The log records real revocations, not repeated logout clicks."""
    _registered_account(factory, identifier="DEL-HASH-12")
    headers = {"Authorization": f"Bearer {_login(client, 'DEL-HASH-12')}"}

    before = core.audit.read("technical")
    client.post("/api/auth/logout", headers=headers)
    written = core.audit.read("technical")[len(before):]
    assert "logout.ok" in written

    before_second = core.audit.read("technical")
    client.post("/api/auth/logout", headers=headers)
    assert core.audit.read("technical") == before_second


# ---------------------------------------------------------------------------
# The Turnstile gate
# ---------------------------------------------------------------------------
# Disabled by default in the test environment (conftest clears TURNSTILE_SECRET). These tests
# turn it on and stub `captcha.verify`, so the endpoint's mapping of the three outcomes is
# exercised without a call to Cloudflare. `verify` itself is unit-tested elsewhere.


@pytest.fixture()
def captcha_on(monkeypatch):
    """Enable the gate the way a production environment does."""
    monkeypatch.setenv("TURNSTILE_SECRET", "test-secret")
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", "localhost")
    assert core.captcha.enabled() is True


def test_login_requires_a_completed_human_check(client, factory, captcha_on, monkeypatch):
    _registered_account(factory, identifier="DEL-HASH-13")
    monkeypatch.setattr(core.captcha, "verify", lambda *a, **k: False)

    response = client.post(
        "/api/auth/login", json={"hash": "DEL-HASH-13", "password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Please complete the human check and try again."}


def test_login_passes_when_the_human_check_verifies(
    client, factory, captcha_on, monkeypatch
):
    _registered_account(factory, identifier="DEL-HASH-14")
    monkeypatch.setattr(core.captcha, "verify", lambda *a, **k: True)

    response = client.post(
        "/api/auth/login",
        json={"hash": "DEL-HASH-14", "password": PASSWORD},
        headers={"X-Turnstile-Token": "a-real-token"},
    )

    assert response.status_code == 200


def test_a_cloudflare_outage_is_503_not_a_failed_check(
    client, factory, captcha_on, monkeypatch
):
    """Failing closed, but telling the visitor the difference between "you failed" and
    "we could not check right now" - one is their fault, the other is ours."""
    _registered_account(factory, identifier="DEL-HASH-15")

    def unavailable(*args, **kwargs):
        raise core.captcha.CaptchaUnavailable("connection timed out")

    monkeypatch.setattr(core.captcha, "verify", unavailable)

    response = client.post(
        "/api/auth/login",
        json={"hash": "DEL-HASH-15", "password": PASSWORD},
        headers={"X-Turnstile-Token": "any-token"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "message": "The human check is unavailable right now. Please try again in a moment."
    }


def test_register_is_gated_by_the_same_check(client, factory, captcha_on, monkeypatch):
    """One widget serves both buttons; a gap on either route would be a gap in the check."""
    _unclaimed_account(factory, identifier="CLAIM-6")
    monkeypatch.setattr(core.captcha, "verify", lambda *a, **k: False)

    response = client.post(
        "/api/auth/register", json={"hash": "CLAIM-6", "password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Please complete the human check and try again."}
