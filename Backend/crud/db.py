import os
from datetime import datetime, timezone

from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL: str = os.getenv("DATABASE_URL", "")  # e.g. postgresql+psycopg2://user:pass@host/db

if not DATABASE_URL:
    # create_engine("") raises a URL-parse error that says nothing about the cause. In a
    # container there is no .env to fall back on, so this is the likely first failure.
    raise SystemExit(
        "DATABASE_URL is not set. Set it in the environment (containers) or in "
        "Backend/crud/.env (local development)."
    )

# Basic logic of this file: This sets up the database connection and session management for SQLAlchemy.
# Each session is basically an interaction between Python and the database. Whenever someone wants to read/update data in the database, Python endpoints see it.
# The endpoints then ask the database; since multiple users can be requesting at the same time, each endpoint/user gets their own session.
# A session stores changes to the databases in RAM. Only when the changes are finished are the changes pushed to the database in storage.

# pre_ping costs one cheap round trip per checkout and saves the first request after a
# Postgres restart (or a dropped connection) from failing on a stale pooled connection.
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db # yields a session to the caller (this is a generator function)
    finally:
        db.close() # guarantees that the session is closed after the caller is done with it, even if an error occurs with the caller's code.

def utcnow() -> datetime:
    """The project's "now" for every timestamp column.

    The schema maps plain `Mapped[datetime]`, i.e. Postgres `timestamp without time
    zone`, so all of them store naive UTC. Comparing an aware datetime
    (`datetime.now(timezone.utc)`) against one of those values raises TypeError in
    Python, and lets Postgres convert by the session's offset if the comparison happens
    in SQL - so window and expiry checks go through this helper.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)