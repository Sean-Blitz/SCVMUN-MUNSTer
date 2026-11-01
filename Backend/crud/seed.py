"""Create the database tables, plus the one row the schema is useless without.

Run this once, after the Postgres database named in DATABASE_URL exists and
before the API is started for the first time:

    python crud/seed.py        # from the Backend/ directory
    # or, equivalently:
    python -m crud.seed

It creates tables and inserts exactly one row: the pinned "Conference Start" timeline
event, whose time is the conference's start and therefore the target of the header
countdown. That row is seeded rather than left to the admin because the countdown and
the timeline's delete protection both assume it exists. Everything else is left empty:
accounts appear when an admin issues hashes (POST /admin/hashes) and each holder claims
theirs through POST /auth/register.

`create_all()` is idempotent - it checks for each table before emitting DDL - and the
seed row is only inserted when it is missing, so re-running this script is safe and never
touches existing data.
"""

import os
import sys

# Allow `python crud/seed.py` as well as `python -m crud.seed`: when a script is
# run directly, sys.path[0] is its own directory (Backend/crud), so the `crud`,
# `core` and `schemas` packages would not resolve. Put Backend/ on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.audit
from core.controls import CONFERENCE_START_LABEL

from crud.database_schema import Base, TimelineEvent
from crud.db import DATABASE_URL, engine, utcnow


def ensure_schema(bind) -> list[str]:
    """Create every table in Base.metadata that is missing; return their names.

    The one place that knows how to make the schema, shared with crud/bootstrap.py so the
    two scripts cannot drift. Safe to call any number of times, and a no-op when the tables
    already exist - `create_all` checks before emitting DDL.

    Raises SystemExit with the driver's own message (Postgres not running, database or
    credentials missing) rather than a bare traceback, because that is the likely cause.
    """
    try:
        Base.metadata.create_all(bind=bind)
    except SQLAlchemyError as exc:
        raise SystemExit(f"Could not create tables: {exc}") from exc

    return sorted(Base.metadata.tables)


def ensure_conference_start(bind, *, lead_days: int = 30) -> bool:
    """Insert the pinned Conference Start event if the timeline has none.

    `lead_days` only picks the placeholder date - the admin sets the real start from the
    Timeline tab, which is the one thing about this row that is editable. Returns whether a
    row was inserted, so callers can report it.

    Shared with crud/bootstrap.py so a bootstrapped database and a seeded one agree.
    """
    with Session(bind) as db:
        existing = db.scalars(
            select(TimelineEvent).where(TimelineEvent.pinned.is_(True))
        ).first()
        if existing is not None:
            return False

        db.add(
            TimelineEvent(
                phase="preConference",
                label=CONFERENCE_START_LABEL,
                starts_at=utcnow() + timedelta(days=lead_days),
                pinned=True,
            )
        )
        db.commit()
        return True


def main() -> None:
    """Create every table in Base.metadata; skip any that already exist."""
    if not DATABASE_URL:
        # crud/db.py reads DATABASE_URL at import time, so reaching this point with
        # an empty value means Backend/crud/.env is missing that key.
        raise SystemExit(
            "DATABASE_URL is not set. Add it to Backend/crud/.env (see crud/db.py)."
        )

    target = engine.url.render_as_string(hide_password=True)
    print(f"Creating tables in {target} ...")

    tables = ensure_schema(engine)

    print("Tables present: " + ", ".join(tables))

    if ensure_conference_start(engine):
        print(
            f"Seeded the pinned '{CONFERENCE_START_LABEL}' event "
            "(placeholder date - set the real time in the Timeline tab)."
        )
    else:
        print(f"'{CONFERENCE_START_LABEL}' already present.")

    # Recorded only when the application has already created its log directory: running
    # this script as another user (root, say) must not leave root-owned 0600 log files
    # that the API then cannot append to.
    if core.audit.log_dir().is_dir():
        core.audit.technical("db.tables_created", tables=len(Base.metadata.tables))


if __name__ == "__main__":
    main()
