from typing import List, Dict, Any

paper_rubric_data: List[Dict[str, Any]] = [] # fill in manually
# Ex: [{"id": "criterion1", "label": "Clarity of Argument", "score": 8, "maxScore": 10}, ...]
award_options = ["Verbal Commendation", "Honorable Mention", "Outstanding Delegate", "Best Delegate"]
awards_rubric: List[Dict[str, Any]] = []
# Ex: [{"id": "string | number", "label": "string", "levels": [{ "score": 4, "label": "string", "description": "string" }]}]
"""Consider making the ones above dynamic by putting them into the database and exposing an endpoint to edit them."""