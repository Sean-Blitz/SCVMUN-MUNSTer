"""Admin use cases for announcements and conference links (§8.6).

These are the lines the delegate dashboard renders. The caps in
`core.controls.BROADCAST_LIMITS` are enforced here rather than in the schema because they
depend on the schedule: a row that has not ended yet can still appear, so it holds a slot,
and an expired one frees it. Counting that way makes the cap an upper bound on what any
delegate can ever see at one instant, which is the whole point of the 2 + 1 / 2 + 3 split.

Caps and kinds are read through `core.controls` at call time, not copied in at import, so
they stay patchable in tests (and could become editable later).
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import core.audit
from core import controls
from core.domain.admin.committees import require_committee
from core.domain.errors import (
    AnnouncementHasUrl,
    BroadcastCapReached,
    BroadcastNotFound,
    EmptyBroadcastBody,
    InvalidBroadcastKind,
    InvertedWindow,
    LinkNeedsUrl,
)
from crud.database_schema import Broadcast
from crud.db import utcnow
from schemas.response_models import BroadcastEntry, BroadcastListResponse


def _kinds() -> tuple[str, ...]:
    return tuple(sorted(controls.BROADCAST_LIMITS))


def _validate_broadcast(
    db: Session, kind: str, body: str, url: str | None, committee_name: str | None
) -> tuple[str, str | None, str | None]:
    """Normalise and check the fields shared by both kinds. Returns the cleaned values."""
    if kind not in controls.BROADCAST_LIMITS:
        raise InvalidBroadcastKind(_kinds())

    body = (body or "").strip()
    if not body:
        raise EmptyBroadcastBody()

    url = (url or "").strip() or None
    if kind == "link" and url is None:
        raise LinkNeedsUrl()
    if kind == "announcement" and url is not None:
        raise AnnouncementHasUrl()

    if committee_name is not None:
        committee_name = committee_name.strip() or None
        if committee_name is not None:
            require_committee(db, committee_name)

    return body, url, committee_name


def _validate_window(starts_at: datetime | None, ends_at: datetime | None) -> None:
    """Reject an inverted schedule before the schema's CHECK constraint sees it."""
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise InvertedWindow()


def _slots_used(
    db: Session, kind: str, committee_name: str | None, exclude_id: int | None = None
) -> int:
    """How many rows of this kind + target can still be shown (i.e. have not ended)."""
    target = (
        Broadcast.committee_name.is_(None)
        if committee_name is None
        else Broadcast.committee_name == committee_name
    )
    stmt = (
        select(func.count())
        .select_from(Broadcast)
        .where(
            Broadcast.kind == kind,
            target,
            or_(Broadcast.ends_at.is_(None), Broadcast.ends_at > utcnow()),
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Broadcast.id != exclude_id)
    return db.scalar(stmt) or 0


def _enforce_cap(
    db: Session, kind: str, committee_name: str | None, exclude_id: int | None = None
) -> None:
    """Refuse a create/edit that would put more lines in front of a delegate than fit."""
    cap = controls.BROADCAST_LIMITS[kind]["global" if committee_name is None else "committee"]
    if _slots_used(db, kind, committee_name, exclude_id) >= cap:
        audience = "for every delegate" if committee_name is None else f"for {committee_name}"
        raise BroadcastCapReached(kind, cap, audience)


def list_broadcasts(db: Session, *, kind: str | None = None) -> BroadcastListResponse:
    """Every broadcast, expired ones included: this is the editor's view."""
    if kind is not None and kind not in controls.BROADCAST_LIMITS:
        raise InvalidBroadcastKind(_kinds())

    stmt = select(Broadcast).order_by(
        Broadcast.kind, Broadcast.committee_name, Broadcast.position, Broadcast.id
    )
    if kind is not None:
        stmt = stmt.where(Broadcast.kind == kind)

    return BroadcastListResponse(
        broadcasts=[BroadcastEntry.model_validate(row) for row in db.scalars(stmt).all()]
    )


def create_broadcast(
    db: Session,
    *,
    kind: str,
    body: str,
    url: str | None,
    committee_name: str | None,
    position: int,
    starts_at: datetime | None,
    ends_at: datetime | None,
    actor: str,
) -> BroadcastEntry:
    """Publish one announcement or conference link, if its target still has room."""
    body, url, committee_name = _validate_broadcast(db, kind, body, url, committee_name)
    _validate_window(starts_at, ends_at)

    # A row with no end date, or one in the future, can still appear, so it counts.
    if ends_at is None or ends_at > utcnow():
        _enforce_cap(db, kind, committee_name)

    broadcast = Broadcast(
        kind=kind,
        body=body,
        url=url,
        committee_name=committee_name,
        position=position,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(broadcast)
    db.commit()
    db.refresh(broadcast)  # created_at is a server default, so it only exists post-insert

    core.audit.business(
        "broadcast.published",
        actor=actor,
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )

    return BroadcastEntry.model_validate(broadcast)


def update_broadcast(
    db: Session, broadcast_id: int, *, changes: dict, actor: str
) -> BroadcastEntry:
    """Edit one broadcast. `kind` is fixed at creation.

    Only the keys present in `changes` are applied, so `"ends_at": None` clears the end date
    while omitting it leaves it alone.
    """
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFound(broadcast_id)

    body, url, committee_name = _validate_broadcast(
        db,
        broadcast.kind,
        changes.get("body", broadcast.body),
        changes.get("url", broadcast.url),
        changes.get("committee_name", broadcast.committee_name),
    )
    starts_at = changes.get("starts_at", broadcast.starts_at)
    ends_at = changes.get("ends_at", broadcast.ends_at)
    _validate_window(starts_at, ends_at)

    # Re-check the cap against the *new* target and schedule: an edit can move a line to a
    # busier committee, or revive an expired one that was not holding a slot.
    if ends_at is None or ends_at > utcnow():
        _enforce_cap(db, broadcast.kind, committee_name, exclude_id=broadcast.id)

    broadcast.body = body
    broadcast.url = url
    broadcast.committee_name = committee_name
    broadcast.starts_at = starts_at
    broadcast.ends_at = ends_at
    broadcast.position = changes.get("position", broadcast.position)
    broadcast.updated_at = utcnow()
    db.commit()

    core.audit.business(
        "broadcast.edited",
        actor=actor,
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )

    return BroadcastEntry.model_validate(broadcast)


def delete_broadcast(db: Session, broadcast_id: int, *, actor: str) -> None:
    """Remove one broadcast outright: announcements keep no history."""
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFound(broadcast_id)

    core.audit.business(
        "broadcast.withdrawn",
        actor=actor,
        id=broadcast.id,
        kind=broadcast.kind,
        target=broadcast.committee_name or "all",
        line=core.audit.short(broadcast.body),
    )
    db.delete(broadcast)
    db.commit()
