import os
from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL: str = os.getenv("DATABASE_URL", "")  # Replace with your actual database URL

# Basic logic of this file: This sets up the database connection and session management for SQLAlchemy.
# Each session is basically an interaction between Python and the database. Whenever someone wants to read/update data in the database, Python endpoints see it.
# The endpoints then ask the database; since multiple users can be requesting at the same time, each endpoint/user gets their own session.
# A session stores changes to the databases in RAM. Only when the changes are finished are the changes pushed to the database in storage.

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db # yields a session to the caller (this is a generator function)
    finally:
        db.close() # guarantees that the session is closed after the caller is done with it, even if an error occurs with the caller's code.