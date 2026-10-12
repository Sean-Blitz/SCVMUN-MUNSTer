import os
from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env file
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, ForeignKey, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from core.controls import paper_rubric_data, award_options, awards_rubric

class Base(DeclarativeBase):
    pass

class Account(Base):
    """Identity and credentials for every role. One row per person who can log in.

    The profile tables (Delegates, Chairs, School) hang off this table one-to-one:
    each of them uses its account_id as its own primary key, so the database
    guarantees exactly one profile row per account.

    `identifier` is the opaque string typed at the login screen (the pre-issued
    "hash" from the organizers). `password_hash` is NULL until the account is
    claimed through /auth/register, which means "is this account registered?" is
    simply `password_hash IS NOT NULL`.
    """
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identifier: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # 'delegate', 'advisor', 'chair', 'admin'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class AuthSession(Base):
    """An active login. One row per token, so one account can be signed in on many devices.

    `token_hash` holds a hash of the issued token rather than the token itself, so a
    database leak does not hand over live sessions. It is looked up on every
    authenticated request, hence the index. Deleting a row logs that device out;
    `ondelete="CASCADE"` clears an account's sessions with the account.
    """
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

class School(Base):
    __tablename__ = "schools"

    # The advisor's account. This doubles as the school's primary key, which is what
    # makes this table one-to-one with Account.
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    school_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    school_address: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    advisor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    advisor_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    advisor_email: Mapped[str] = mapped_column(String(100), nullable=False)
    head_delegate_name: Mapped[str] = mapped_column(String(100), nullable=False)
    head_delegate_email: Mapped[str] = mapped_column(String(100), nullable=False)
    head_delegate_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    invoiceURL: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'paid', 'partially paid', 'unpaid'
    check_list: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    delegates = relationship("Delegates", backref="school", cascade="all, delete-orphan")

class Committees(Base):
    __tablename__ = "committees"

    committee_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    chairs = relationship("Chairs", backref="committee", cascade="all, delete-orphan")
    delegates = relationship("Delegates", backref="committee_record", cascade="all, delete-orphan")
    timeline: Mapped[Optional[Dict[str, List[Dict[str, Any]]]]] = mapped_column(JSONB, nullable=True)  
    # e.g., {"preConference": [{"event": "Opening Ceremony", "date": "ISO-8601"}, ...], "duringConference": [{"event": "Committee Session 1", "date": "ISO-8601"}, ...]}
    # timeline must contain both keys even when empty.

class Chairs(Base):
    __tablename__ = "chairs"

    # The chair's account. Doubles as this table's primary key (one-to-one with Account).
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    committee_name: Mapped[str] = mapped_column(String(100), ForeignKey("committees.committee_name"), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False)

class Delegates(Base):
    __tablename__ = "delegates"

    # The delegate's account. Doubles as this table's primary key (one-to-one with Account).
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    country: Mapped[str] = mapped_column(String(100), nullable=False)
    committee: Mapped[str] = mapped_column(String(100), ForeignKey("committees.committee_name"), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.account_id"), nullable=False)
    # ↑ references the owning advisor's account, which is the schools table's primary key

    # Note: regarding papers, they should not be able to be re-submitted after the grade has been given.
    paper_status: Mapped[str] = mapped_column(String(100), nullable=False, default="unsubmitted") # i.e. 'unsubmitted', 'submitted', 'graded'
    position_papers: Mapped[List["Uploads"]] = relationship(back_populates="delegate", cascade="all, delete-orphan")
    paper_grade: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # i.e. "18/20"
    paper_comments: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    paper_rubric_grade: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    assigned_award: Mapped[str] = mapped_column(String(100), nullable=False, default="None")
    # i.e. "Candidate | Verbal Commendation | Honorable Mention | Outstanding Delegate | Best Delegate | None"
    overall_rubric_scores: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    overall_total_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Uploads(Base):
    """Represents a file upload by a delegate. Every time a delegate uploads a new position paper, a new record is created here. The file itself is stored in the filesystem, and the path is recorded in this table."""
    __tablename__ = "position_papers"

    upload_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delegate_id: Mapped[int] = mapped_column(Integer, ForeignKey("delegates.account_id"), nullable=False)
    upload_time: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(256), nullable=False)
    # The actual URL returned to the frontend will be constructed by here, done through signed URL.

    delegate: Mapped["Delegates"] = relationship("Delegates", back_populates="position_papers")
