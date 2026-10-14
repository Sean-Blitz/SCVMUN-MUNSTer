from typing import List, Dict, Any

paper_rubric_data: List[Dict[str, Any]] = [] # fill in manually
# Ex: [{"id": "criterion1", "label": "Clarity of Argument", "score": 8, "maxScore": 10}, ...]
award_options = ["Verbal Commendation", "Honorable Mention", "Outstanding Delegate", "Best Delegate"]
awards_rubric: List[Dict[str, Any]] = []
# Ex: [{"id": "string | number", "label": "string", "levels": [{ "score": 4, "label": "string", "description": "string" }]}]
"""Consider making the ones above dynamic by putting them into the database and exposing an endpoint to edit them."""

# --- Delegate-facing broadcasts (announcements & conference links) ---
# How many not-yet-ended rows each target may have at once. A "global" row
# (committee_name IS NULL) reaches every delegate; a "committee" row reaches only that
# committee's delegates. Counting rows that have not ended yet - rather than rows that
# are live right now - is what bounds what a delegate can see at any instant: a row
# scheduled to start later still holds its slot, and an expired one frees it.
# The totals match the delegate dashboard: 3 announcement lines, 5 link slots.
BROADCAST_LIMITS: Dict[str, Dict[str, int]] = {
    "announcement": {"global": 2, "committee": 1},
    "link": {"global": 2, "committee": 3},
}
# The two halves of the conference timeline the chair dashboard renders, in the order it
# expects them. Kept here because both the admin editor (which validates `phase`) and the
# chair overview (which must always return both keys, even when empty) need the same list.
TIMELINE_PHASES = ("preConference", "duringConference")
