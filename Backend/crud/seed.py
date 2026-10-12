"""Create the database tables described by crud/database_schema.py.

Run this once, after the Postgres database named in DATABASE_URL exists and
before the API is started for the first time:

    python crud/seed.py        # from the Backend/ directory
    # or, equivalently:
    python -m crud.seed

It creates tables and nothing else: no rows are inserted, so the database is left
empty. Accounts appear later, when an admin issues hashes (POST /admin/hashes) and
each holder claims theirs through POST /auth/register.

`create_all()` is idempotent - it checks for each table before emitting DDL - so
re-running this script is safe and never touches existing data.
"""

import os
import sys

# Allow `python crud/seed.py` as well as `python -m crud.seed`: when a script is
# run directly, sys.path[0] is its own directory (Backend/crud), so the `crud`,
# `core` and `schemas` packages would not resolve. Put Backend/ on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.exc import SQLAlchemyError

from crud.database_schema import Base
from crud.db import DATABASE_URL, engine


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

    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        # Most often: Postgres is not running, or the database/credentials in
        # DATABASE_URL do not exist yet. Surface the driver's message instead of a
        # bare traceback.
        raise SystemExit(f"Could not create tables: {exc}") from exc

    print("Tables present: " + ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
