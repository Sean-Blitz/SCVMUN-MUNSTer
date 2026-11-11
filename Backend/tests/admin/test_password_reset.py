"""POST /admin/accounts/{id}/reset-password.

A hash is the login code; a password is what its holder chose at registration. They live on
the same row but neither derives from the other, so resetting a password is its own
operation: it clears `password_hash` (back to the unclaimed state) and ends the sessions,
after which the same hash claims the account again through First-Time Register.
"""

from sqlalchemy import select

from crud.database_schema import AuthSession


def _admin_headers(factory):
    admin = factory.account(role="admin", name="Admin Person", identifier="ADMIN-0001")
    return factory.headers(admin)


def test_reset_clears_the_password_and_the_sessions(client, factory, delegate, delegate_account):
    """The account goes back to unclaimed, the old token dies, and the hash still works."""
    delegate_account.password_hash = "some-existing-hash"
    factory.db.commit()

    delegate_headers = factory.headers(delegate_account)  # a live session to revoke
    admin_headers = _admin_headers(factory)

    response = client.post(
        f"/api/admin/accounts/{delegate_account.id}/reset-password", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "name": delegate_account.name,
        "role": "delegate",
        "hash": delegate_account.identifier,  # the hash itself is untouched
    }

    factory.db.expire_all()
    account = factory.db.get(type(delegate_account), delegate_account.id)
    assert account.password_hash is None
    assert factory.db.scalars(select(AuthSession).where(AuthSession.account_id == account.id)).all() == []

    # The revoked token no longer authenticates.
    assert client.get("/api/delegate/my-assignment", headers=delegate_headers).status_code == 401

    # And the unchanged hash claims the account again, with a new password.
    claim = client.post(
        "/api/auth/register",
        json={"hash": delegate_account.identifier, "password": "Str0ng!pass"},
    )
    assert claim.status_code == 200
    assert claim.json()["user"]["role"] == "delegate"


def test_reset_is_refused_when_the_account_never_registered(client, factory, delegate_account):
    """An unclaimed hash has no password to clear; saying "done" would be misleading."""
    admin_headers = _admin_headers(factory)

    response = client.post(
        f"/api/admin/accounts/{delegate_account.id}/reset-password", headers=admin_headers
    )

    assert response.status_code == 409
    assert "not registered" in response.json()["message"]


def test_reset_of_an_unknown_account_is_404(client, factory):
    response = client.post("/api/admin/accounts/999999/reset-password", headers=_admin_headers(factory))
    assert response.status_code == 404
    assert response.json()["message"] == "No account has that id."


def test_reset_is_admin_only(client, delegate_account):
    delegate_account.password_hash = "some-existing-hash"
    response = client.post(f"/api/admin/accounts/{delegate_account.id}/reset-password")
    # No token at all: authentication fails before the role check.
    assert response.status_code == 401
