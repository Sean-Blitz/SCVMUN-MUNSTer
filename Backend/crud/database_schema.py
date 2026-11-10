import os
from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env file
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Boolean, Float, ForeignKey, CheckConstraint, Index, create_engine, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

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
    """One committee: its name, plus what it is about.

    The name is the primary key because every other table points at a committee *by name*
    (`delegates.committee`, `chairs.committee_name`, `broadcasts.committee_name`), which is
    also why renaming one has to repoint those rows in a single transaction - nothing here
    cascades on update.

    `committee_type` and `topic` are optional: a committee is usable the moment it has a
    name, but the admin needs somewhere to record whether it is a General Assembly body or a
    crisis committee, and what it is debating. The legacy CLI sent a per-delegate
    `committeeType` that had no column to land in; this is where that value belongs, once per
    committee rather than once per delegate.
    """
    __tablename__ = "committees"

    committee_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    committee_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    chairs = relationship("Chairs", backref="committee", cascade="all, delete-orphan")
    delegates = relationship("Delegates", backref="committee_record", cascade="all, delete-orphan")

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
    # Float, not Integer: the total is the sum of the rubric level scores and the API
    # treats it as a number (AwardDelegate.totalScore), so a fractional mark must not be
    # silently rounded on the way in.
    overall_total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


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


class TimelineEvent(Base):
    """One dated point on the conference schedule, shared by every committee.

    Universal rather than per committee: every chair's overview shows the same run of
    show. `phase` splits it into the run-up and the conference itself, which the chair
    dashboard renders as two lists.

    There is no completion flag and no per-chair tick - an event's state is derived from
    the clock. That is also why ordering matters: the view treats each event's time as
    the start of a window that runs until the next event, so rows are read in ascending
    `starts_at` order and the last pre-conference event bridges into the first
    during-conference one.

    `starts_at` is naive UTC like every other timestamp column (see crud/db.utcnow); the
    chair response marks it as UTC so a browser does not read it as local time.
    """
    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('preConference', 'duringConference')", name="ck_timeline_phase"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(nullable=False)

    # True for the single "Conference Start" row, whose time is the conference's start and
    # therefore the target of the header countdown. It can be re-dated but not deleted or
    # renamed; PUT /admin/timeline enforces that. Seeded by crud/seed.py.
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())


class Rubric(Base):
    """One conference-wide rubric, stored as a single JSON document.

    `kind` is the primary key: `'paper'` holds flat `{id, label, maxScore}` criteria (the
    shape GET /chair/rubric publishes) and `'awards'` holds `{id, label, levels[]}` (the
    shape GET /chair/awards/rubric publishes).

    Stored as one JSONB array rather than a criteria table on purpose: a rubric is read as
    a whole and written as a whole, nothing ever queries by criterion, and `levels` is
    nested - normalising it would buy nothing and cost a join on every grading request.
    The editor sends the array back verbatim (PUT /admin/rubrics).

    `id` inside the array is load-bearing: every stored mark is filed under it
    (`delegates.paper_rubric_grade`, `delegates.overall_rubric_scores`), which is why the
    admin endpoint refuses a save that would drop an id already being graded.

    A missing row means "never edited": readers fall back to the in-code defaults in
    core.controls, so a database seeded before this table existed behaves as it used to.
    """
    __tablename__ = "rubrics"

    kind: Mapped[str] = mapped_column(String(20), primary_key=True)  # 'paper' | 'awards'
    items: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    # Who saved it last, as `role:id` (core.audit.actor). The audit log holds the history;
    # this is only what the editor's footer shows.
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
