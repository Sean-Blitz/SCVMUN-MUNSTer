from typing import List, Dict, Any

# --- The two rubrics ---------------------------------------------------------------------
# These are now *defaults*, not the live rubric. Both documents live in the `rubrics` table
# and are edited from the admin dashboard (PUT /admin/rubrics, §8.11 of the contract), so
# changing a criterion is a UI action rather than an edit here and a restart.
#
# They still matter in two places:
#   1. crud/seed.py copies them in when the row is missing, so whatever was hand-written
#      here before the table existed lands in the database instead of being lost;
#   2. core/domain/rubrics.py falls back to them when a database has no row at all, which is
#      what keeps a test that monkeypatches these attributes in control of the rubric.
#
# Read at call time for that second reason - do not `from core.controls import ...` a rubric
# anywhere, or a patched value will be silently ignored.
paper_rubric_data: List[Dict[str, Any]] = []
# Ex: [{"id": "criterion1", "label": "Clarity of Argument", "maxScore": 10}, ...]
award_options = ["Verbal Commendation", "Honorable Mention", "Outstanding Delegate", "Best Delegate"]
awards_rubric: List[Dict[str, Any]] = []
# Ex: [{"id": "string | number", "label": "string", "levels": [{ "score": 4, "label": "string", "description": "string" }]}]

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

# How many position papers one delegate may upload in a rolling hour. Each upload costs up
# to PAPER_MAX_MB, and re-uploading is allowed until the paper is graded, so without a cap
# a valid token could churn the disk. The old file is deleted on each re-upload
# (see API/Endpoints/delegates.py), so the steady state is one stored paper per delegate.
MAX_UPLOADS_PER_HOUR = 5

# The one timeline event the admin cannot delete or rename: its `starts_at` is the
# conference's start time, which the header countdown reads. Seeded by crud/seed.py and
# protected in PUT /admin/timeline.
CONFERENCE_START_LABEL = "Conference Start"
