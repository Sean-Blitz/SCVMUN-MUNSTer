"""Fixtures for the admin tests.

Every ``/admin`` route sits behind ``require_roles("admin")``, so each file here needs an
admin account and its header. Building them once keeps each test about its own subject.
"""

import pytest


@pytest.fixture()
def admin(factory):
    """An admin account. The identifier is generated, so tests can create several."""
    return factory.account(role="admin", name="Admin Person")


@pytest.fixture()
def admin_headers(factory, admin):
    """Authorization header for that admin."""
    return factory.headers(admin)
