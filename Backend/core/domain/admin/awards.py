"""Admin award report (§8.5).

This is the conference-wide read over the awards chairs assign
(`core.domain.chairs.assign_award`); the chair-facing, writable routes stay with the chair
domain. The report lists what each committee has actually handed out, so a delegate with no
assignment does not appear.

`"None"` is the frontend's own "no award" marker, not an award, so it is filtered out - as
is a NULL assignment (nothing decided yet). `"Candidate"` is kept: it is a shortlist
decision an admin may want to see while the committee is still deciding.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.database_schema import Delegates
from schemas.response_models import AwardEntry, AwardsOverviewResponse, CommitteeAwards


def get_awards_overview(db: Session) -> AwardsOverviewResponse:
    """Every committee's current award assignments, as country + award pairs.

    One query, grouped in Python: the number of assignments is bounded by the number of
    delegates, so a `GROUP BY` would only trade clarity for nothing.
    """
    rows = db.execute(
        select(Delegates.committee, Delegates.country, Delegates.assigned_award)
        .where(
            Delegates.assigned_award.is_not(None),
            Delegates.assigned_award != "None",
        )
        .order_by(Delegates.committee, Delegates.country)
    ).all()

    grouped: dict[str, list[AwardEntry]] = {}
    for committee, country, award in rows:
        grouped.setdefault(committee, []).append(
            AwardEntry(country=country, award=award)
        )

    return AwardsOverviewResponse(
        committees=[
            CommitteeAwards(committee=committee, awards=awards)
            for committee, awards in grouped.items()
        ]
    )
