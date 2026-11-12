"""Fixtures for the chair tests.

A chair account on its own is useless: every chair use case resolves the caller's committee
from the ``chairs`` row and raises ``ChairNotFound`` (404) without it. Building the account
and the profile together is therefore the only sensible default, which is what ``chair``
gives; ``make_chair`` is there for the tests that need a second committee.
"""

import pytest

from crud.database_schema import Chairs


@pytest.fixture()
def make_chair(factory):
    """Build a chair account plus its profile row for a given committee."""

    def _make(committee, *, name="Chair Person", email="chair@example.test"):
        account = factory.account(role="chair", name=name)
        factory.db.add(
            Chairs(
                account_id=account.id,
                name=name,
                committee_name=committee.committee_name,
                email=email,
            )
        )
        factory.db.commit()
        return account

    return _make


@pytest.fixture()
def chair(make_chair, committee):
    """A chair for the default DISEC committee."""
    return make_chair(committee)


@pytest.fixture()
def chair_headers(factory, chair):
    """Authorization header for that chair."""
    return factory.headers(chair)
