import os
from dotenv import load_dotenv; load_dotenv()  # Load environment variables from .env file
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, ForeignKey, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")  # Replace with your actual database URL


class Base(DeclarativeBase):
    pass

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

paper_rubric_data: List[Dict[str, Any]] = [] # fill in manually
# Ex: [{"id": "criterion1", "label": "Clarity of Argument", "score": 8, "maxScore": 10}, ...]
award_options = ["Verbal Commendation", "Honorable Mention", "Outstanding Delegate", "Best Delegate"]
awards_rubric: List[Dict[str, Any]] = []
# Ex: [{"id": "string | number", "label": "string", "levels": [{ "score": 4, "label": "string", "description": "string" }]}]
"""Consider making the ones above dynamic by putting them into the database and exposing an endpoint to edit them."""

class School(Base):
    __tablename__ = "schools"

    school_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    school_address: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    advisor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    advisor_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    advisor_email: Mapped[str] = mapped_column(String(100), nullable=False)
    advisor_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    advisor_password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    head_delegate_name: Mapped[str] = mapped_column(String(100), nullable=False)
    head_delegate_email: Mapped[str] = mapped_column(String(100), nullable=False)

    invoiceURL: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'paid', 'partially paid', 'unpaid'
    check_list: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    delegates = relationship("Delegates", backref="school", cascade="all, delete-orphan")

class Committees(Base):
    __tablename__ = "committees"

    committee_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    chairs = relationship("Chairs", backref="committee", cascade="all, delete-orphan")
    delegates = relationship("Delegates", backref="committee", cascade="all, delete-orphan")
    timeline: Mapped[Optional[Dict[str, List[Dict[str, Any]]]]] = mapped_column(JSONB, nullable=True)  
    # e.g., {"preConference": [{"event": "Opening Ceremony", "date": "ISO-8601"}, ...], "duringConference": [{"event": "Committee Session 1", "date": "ISO-8601"}, ...]}
    # timeline must contain both keys even when empty.

class Chairs(Base):
    __tablename__ = "chairs"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    committee_name: Mapped[str] = mapped_column(String(100), ForeignKey("committees.committee_name"), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    hash: Mapped[str] = mapped_column(String(100), nullable=False, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    
class Logins(Base):
    __tablename__ = "logins"

    id_hash: Mapped[str] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'delegate', 'chair', 'admin'
    last_login: Mapped[Optional[datetime]] = mapped_column(nullable=True)

class Delegates(Base):
    __tablename__ = "delegates"

    id_hash: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    committee: Mapped[str] = mapped_column(String(100), ForeignKey("committees.committee_name"), nullable=False)
    school: Mapped[str] = mapped_column(String(100), ForeignKey("schools.school_name"), nullable=False)

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
    delegate_id: Mapped[int] = mapped_column(Integer, ForeignKey("delegates.id_hash"), nullable=False)
    upload_time: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(256), nullable=False)
    # The actual URL returned to the frontend will be constructed by here, done through signed URL.

    delegate: Mapped["Delegates"] = relationship("Delegates", back_populates="position_papers")