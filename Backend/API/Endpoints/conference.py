"""The conference's start time, for the header countdown.

Public on purpose: the countdown sits in the global header, and the login page shows it
too, so it cannot require a token. It exposes nothing but a date that the organisers
announce anyway.

Read-only. The single source of truth is the pinned `timeline_events` row, which the admin
re-dates from the Timeline tab.
"""

from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.controls import CONFERENCE_START_LABEL
from crud.database_schema import TimelineEvent
from crud.db import get_db
from schemas.response_models import ConferenceStartResponse

router = APIRouter(prefix="/conference", tags=["conference"])


@router.get("", response_model=ConferenceStartResponse)
def get_conference_start(db: Annotated[Session, Depends(get_db)]) -> ConferenceStartResponse:
    """When the conference starts, as an ISO-8601 instant in UTC.

    `starts_at` is null when the pinned event is missing (a database that was never
    seeded), so the header can hide the countdown rather than invent a date.
    """
    row = db.scalars(select(TimelineEvent).where(TimelineEvent.pinned.is_(True))).first()

    if row is None:
        return ConferenceStartResponse(label=CONFERENCE_START_LABEL, starts_at=None)

    # The column is naive UTC; the offset is attached so a browser does not read it as
    # local time. Naive ISO would be off by the client's timezone offset.
    instant = row.starts_at.replace(tzinfo=timezone.utc).isoformat()
    return ConferenceStartResponse(label=row.label, starts_at=instant)
