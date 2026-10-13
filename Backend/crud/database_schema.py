import os
from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env file
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Boolean, ForeignKey, CheckConstraint, Index, create_engine, func
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

    delegates = relationship("Delegates", backref="school", cascade="all, delete-orphan")

class Committees(Base):
    __tablename__ = "committees"

    committee_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    chairs = relationship("Chairs", backref="committee", cascade="all, delete-orphan")
    delegates = relationship("Delegates", backref="committee_record", cascade="all, delete-orphan")
    timeline: Mapped[Optional[Dict[str, List[Dict[str, Any]]]]] = mapped_column(JSONB, nullable=True)  
    # e.g., {"preConference": [{"event": "Opening Ceremony", "date": "ISO-8601"}, ...], "duringConference": [{"event": "Committee Session 1", "date": "ISO-8601"}, ...]}
    # timeline must contain both keys even when empty.

class Broadcast(Base):
    """An admin-authored line shown to delegates: an announcement, or a conference link.

    `kind` decides which strip a row belongs to. A NULL `committee_name` means the row
    goes to every delegate; otherwise it goes only to delegates in that committee.

    The caps that keep a delegate's bar and link strip from overflowing
    (2 global + 1 committee announcement, 2 global + 3 committee links) live in the
    admin endpoints, not here: "how many are allowed" counts only the rows whose
    schedule window covers the moment of the request, which a CHECK constraint cannot
    express. The schema's job is one row per published line.

    `starts_at` NULL means "live immediately"; `ends_at` NULL means "no planned end".
    Deleting a row removes it outright: announcements carry no history and no
    soft-delete flag.
    """
    __tablename__ = "broadcasts"
    __table_args__ = (
        # Every read is "this kind + this committee (or global) + in window", so one
        # composite index serves both the delegate query and the admin list; a
        # kind-only lookup uses its prefix.
        Index("ix_broadcasts_kind_committee", "kind", "committee_name"),
        CheckConstraint("kind IN ('announcement', 'link')", name="ck_broadcasts_kind"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
            name="ck_broadcasts_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'announcement' | 'link'
    body: Mapped[str] = mapped_column(String(300), nullable=False)  # announcement text, or the link's label
    url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # links only
    committee_name: Mapped[Optional[str]] = mapped_column(
        ForeignKey("committees.committee_name", ondelete="CASCADE"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # display order within the strip
    starts_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

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


class ConferenceChecklist(Base):
    """One line of the conference-wide action checklist.

    Shared by every school, not stored per school: the steps ("submit position papers",
    "pay the conference fee") are the same for everyone, and an admin edits them once.
    `position` is explicit so the panel has a stable order.

    Whether a line is *ticked* is not here - that is per school, in ChecklistProgress.
    The pair is why the admin route reconciles lines by `id` rather than deleting and
    re-inserting them: a line's id is what its schools' progress rows point at.
    """
    __tablename__ = "conference_checklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ChecklistProgress(Base):
    """Whether one school has ticked one checklist line.

    Separate from ConferenceChecklist because the labels are shared but progress is not:
    Lincoln paying its invoice must not tick Rival's box. A pair with no row reads as
    "not done", so the table only ever holds ticks that were set (or explicitly cleared).
    Both foreign keys cascade, so removing a school or a checklist line takes its progress
    rows with it.
    """
    __tablename__ = "checklist_progress"

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.account_id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("conference_checklist.id", ondelete="CASCADE"), primary_key=True
    )
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
