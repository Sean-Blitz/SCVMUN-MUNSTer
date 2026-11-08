"""Shared fixtures for the delegate tests - both the API tests and the domain tests.

Three things have to be true before a single test runs, and all three are set up at
*import time* in this file, before anything from the application is imported:

1. ``DATABASE_URL`` points at a **test** database, not the development one. The app's
   engine is built once, when ``crud.db`` is imported, so the variable has to be in
   ``os.environ`` before that import happens. That is why the environment block sits above
   the ``from main import app`` line and not inside a fixture.

2. ``PAPER_UPLOAD_DIR`` and ``LOG_DIR`` point at throwaway directories. Uploads and audit
   lines are real file writes: without this, running the suite fills ``Backend/logs`` and
   ``Backend/crud/pdf_uploads`` with test noise.

3. The Turnstile check is **off**. It is switched on by the presence of
   ``TURNSTILE_SECRET``, which the developer's ``Backend/crud/.env`` does contain, so it
   must be cleared here or every login-shaped test would try to call Cloudflare.

The test database is derived from the developer's own ``DATABASE_URL`` by renaming the
database to ``<name>_test``, so no credentials live in this file. It is created on demand,
and the name is checked to contain "test" before any schema is touched - the guard exists
so a misconfigured run can never truncate a real conference database.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

# `main:app` and the `core`/`crud`/`API` packages only import when Backend/ is on the path.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ENV_FILE = BACKEND_DIR / "crud" / ".env"

# Throwaway locations for everything the app writes. One per test session, emptied between
# tests by `clean_database` below.
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="scvmun-tests-"))
PAPER_DIR = _TMP_ROOT / "papers"
LOG_DIR = _TMP_ROOT / "logs"
PAPER_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _test_database_url() -> URL:
    """The URL of the database this suite is allowed to destroy.

    Order: an explicit ``TEST_DATABASE_URL``, otherwise the developer's ``DATABASE_URL``
    with ``_test`` appended to the database name.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        raw = dotenv_values(ENV_FILE).get("DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not raw:
            raise SystemExit(
                f"Neither TEST_DATABASE_URL nor DATABASE_URL is set. "
                f"Expected DATABASE_URL in {ENV_FILE}."
            )
        base = make_url(raw.strip())
        if base.database and base.database.endswith("_test"):
            url = base
        else:
            url = base.set(database=f"{base.database}_test")

    # The guard that makes this file safe to run: every table in the test database gets
    # truncated between tests, so the name must be unmistakably a test database.
    if not url.database or "test" not in url.database:
        raise SystemExit(
            f"Refusing to run tests against database {url.database!r}: "
            "the name must contain 'test'."
        )
    return url


def _ensure_database_exists(url: URL) -> None:
    """Create the test database if it is not there yet.

    ``CREATE DATABASE`` cannot run inside a transaction, hence the autocommit connection to
    the maintenance database. Connecting to the *target* database to ask "do you exist?"
    is not possible, so ``pg_database`` is the source of truth.
    """
    connection = psycopg2.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname="postgres",
    )
    connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,))
            if cursor.fetchone() is None:
                cursor.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        connection.close()


TEST_DATABASE_URL = _test_database_url()
_ensure_database_exists(TEST_DATABASE_URL)

# --- Environment, set before the application is imported. See the module docstring. ---
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ["PAPER_UPLOAD_DIR"] = str(PAPER_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)
os.environ["TURNSTILE_SECRET"] = ""
os.environ["TURNSTILE_HOSTNAMES"] = ""

# Imported only now that the environment is correct.
from fastapi.testclient import TestClient  # noqa: E402

import core.security  # noqa: E402
from crud.db import SessionLocal, engine, utcnow  # noqa: E402
from crud.database_schema import (  # noqa: E402
    Account,
    AuthSession,
    Base,
    Broadcast,
    Committees,
    Delegates,
    School,
    Uploads,
)
from main import app  # noqa: E402

# Every table, quoted, for the per-test TRUNCATE. Built from the metadata rather than
# hand-listed so a new table is cleaned up automatically.
_TABLES = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)


# ---------------------------------------------------------------------------
# Schema and per-test isolation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def schema():
    """Drop and recreate every table once per session.

    ``drop_all`` first, not just ``create_all``: ``create_all`` skips tables that already
    exist, so a schema left over from an older revision of the models would silently keep
    its old columns. Recreating is the cheap fix that makes a stale test database
    self-healing.
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    # Left in place on purpose: a failed run is easier to inspect if its rows are still
    # there. The next run drops them.


@pytest.fixture(autouse=True)
def clean_database(schema):
    """Start every test from an empty database and an empty upload directory.

    This is an autouse fixture, so it runs before each test without being requested.

    A transaction-per-test rollback - the usual way to isolate tests - is **not** usable
    here: the domain functions commit (``core.domain.delegates.submit_paper`` calls
    ``db.commit()``), which ends the test's transaction. Truncating between tests is the
    remaining option, and it is honest about what the code does.
    """
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))

    for stale in PAPER_DIR.iterdir():
        if stale.is_file():
            stale.unlink()

    yield


@pytest.fixture()
def db():
    """A session for the test body itself, separate from the one the request uses.

    Two sessions against one database, which is exactly the situation in production: the
    test writes its fixture data and commits it, then the request reads it through the
    app's own session.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    """The FastAPI app behind Starlette's TestClient.

    Deliberately *not* used as a context manager: entering ``with TestClient(app)`` runs
    the app's lifespan hook, which starts the heartbeat thread and writes to ``LOG_DIR``
    for the duration of the suite. Tests that need startup behaviour can opt in
    explicitly.
    """
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


# ---------------------------------------------------------------------------
# Building a world to test against
# ---------------------------------------------------------------------------


class Factory:
    """Small builders for the rows the delegate endpoints need.

    Everything commits, because the request runs in its own session and has to be able to
    see the data.
    """

    def __init__(self, session):
        self.db = session

    def account(
        self,
        *,
        role: str = "delegate",
        name: str = "Test Person",
        identifier: str | None = None,
        password_hash: str | None = None,
    ) -> Account:
        account = Account(
            identifier=identifier or f"{role}-{uuid.uuid4().hex[:8]}",
            role=role,
            name=name,
            password_hash=password_hash,
        )
        self.db.add(account)
        self.db.commit()
        return account

    def token(self, account: Account, *, lifetime: timedelta = timedelta(hours=1)) -> str:
        """Issue a session token, the way ``/auth/login`` does.

        The token is created directly rather than by calling the login endpoint: these
        tests are about the delegate routes, and going through login would couple every
        one of them to the password rules and the Turnstile header.
        """
        token = core.security.new_token()
        self.db.add(
            AuthSession(
                account_id=account.id,
                token_hash=core.security.hash_token(token),
                expires_at=utcnow() + lifetime,
            )
        )
        self.db.commit()
        return token

    def headers(self, account: Account, **kwargs) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(account, **kwargs)}"}

    def committee(self, name: str = "DISEC") -> Committees:
        committee = Committees(committee_name=name)
        self.db.add(committee)
        self.db.commit()
        return committee

    def school(self, advisor: Account, name: str = "Test High School") -> School:
        school = School(
            account_id=advisor.id,
            school_name=name,
            school_address="1 Test Way",
            city="Testville",
            state="CA",
            zip_code="90000",
            advisor_name=advisor.name,
            advisor_phone="555-0100",
            advisor_email="advisor@example.test",
            head_delegate_name="Head Delegate",
            head_delegate_email="head@example.test",
            head_delegate_phone="555-0101",
            payment_status="unpaid",
        )
        self.db.add(school)
        self.db.commit()
        return school

    def delegate(
        self,
        account: Account,
        *,
        committee: Committees,
        school: School,
        country: str = "France",
        **fields,
    ) -> Delegates:
        delegate = Delegates(
            account_id=account.id,
            country=country,
            committee=committee.committee_name,
            school_id=school.account_id,
            **fields,
        )
        self.db.add(delegate)
        self.db.commit()
        return delegate


    def upload(
        self,
        delegate: Delegates,
        *,
        when=None,
        file_name: str = "previous-paper.pdf",
        file_path: str = "previous-paper.pdf",
        write_bytes: bytes | None = None,
    ) -> Uploads:
        """Insert a ``position_papers`` row, optionally with bytes behind it.

        The domain never creates a row without a file, but a *test* often wants one of the
        two without the other - and a row whose file is missing is a real production state
        (a half-restored volume), so it needs to be expressible.
        """
        if write_bytes is not None:
            target = PAPER_DIR / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(write_bytes)

        row = Uploads(
            delegate_id=delegate.account_id,
            file_name=file_name,
            file_path=file_path,
            upload_time=when or utcnow(),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def broadcast(
        self,
        *,
        kind: str = "announcement",
        body: str = "Test line",
        committee: Committees | None = None,
        position: int = 0,
        starts_at=None,
        ends_at=None,
        url: str | None = None,
    ) -> Broadcast:
        row = Broadcast(
            kind=kind,
            body=body,
            url=url,
            committee_name=committee.committee_name if committee else None,
            position=position,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self.db.add(row)
        self.db.commit()
        return row


@pytest.fixture()
def factory(db) -> Factory:
    return Factory(db)


@pytest.fixture()
def committee(factory) -> Committees:
    return factory.committee("DISEC")


@pytest.fixture()
def advisor(factory) -> Account:
    return factory.account(role="advisor", name="Advisor Person", identifier="ADV-0001")


@pytest.fixture()
def school(factory, advisor) -> School:
    return factory.school(advisor)


@pytest.fixture()
def delegate_account(factory) -> Account:
    return factory.account(role="delegate", name="Delegate Person", identifier="DEL-0001")


@pytest.fixture()
def delegate(factory, delegate_account, committee, school) -> Delegates:
    return factory.delegate(delegate_account, committee=committee, school=school)


@pytest.fixture()
def delegate_headers(factory, delegate_account, delegate) -> dict[str, str]:
    """Authorization header for the delegate built above.

    Depends on ``delegate`` as well as the account so that every test asking for headers
    also gets the profile row the endpoints look up.
    """
    return factory.headers(delegate_account)


@pytest.fixture()
def advisor_headers(factory, advisor, school) -> dict[str, str]:
    """Authorization header for a correctly authenticated *advisor*.

    Used to prove the role gate, not just "no token": a valid token of the wrong role must
    be refused too.
    """
    return factory.headers(advisor)


# A tiny, valid-looking PDF: the domain only checks the ``%PDF-`` signature, and the tests
# that care about content read the bytes back out.
PDF_BYTES = b"%PDF-1.4\n% test paper\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def pdf_upload(name: str = "position-paper.pdf", content: bytes = PDF_BYTES):
    """The ``files=`` argument for a multipart upload of a PDF."""
    return {"paper": (name, content, "application/pdf")}


@pytest.fixture()
def papers_dir() -> Path:
    """The directory the app writes uploads to during the suite."""
    return PAPER_DIR


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp_root():
    yield
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)
