"""Domain tests for ``core.domain.delegates.get_delegate_dashboard``.

No HTTP here: the use case is called with a database session and its return value is
inspected directly. That is deliberate. The dashboard's *rules* - which broadcasts a
delegate sees, in what order, and when rubric marks are allowed out - are the interesting
part, and they can be pinned without a client, a token, or a status code in sight.

The equivalent API-level coverage lives in ``test_endpoints.py``; when a rule breaks, this
file should be the one that says which rule.
"""

from datetime import timedelta

from core import controls
from core.domain import delegates as domain
from crud.db import utcnow

# --- the profile -----------------------------------------------------------------------


def test_returns_none_when_the_account_has_no_delegate_profile(db, factory):
    """An account can hold a delegate token and still have no profile row.

    ``None`` rather than an exception is the domain's choice: "no profile" has exactly one
    HTTP meaning (404) and no data to hand back, so the endpoint maps it. Every other
    failure in this module is an exception because it carries data.
    """
    account = factory.account(role="delegate", identifier="NO-PROFILE-1")

    assert domain.get_delegate_dashboard(db, account.id) is None


def test_reports_the_delegates_committee_and_country(db, delegate):
    payload = domain.get_delegate_dashboard(db, delegate.account_id)

    assert payload.delegate.committee == "DISEC"
    assert payload.delegate.country == "France"


# --- announcements ---------------------------------------------------------------------


def test_general_lines_come_first_then_the_committees_own(db, factory, delegate, committee):
    """Global announcements sort ahead of committee ones, regardless of ``position``.

    ``position`` only competes *within* a strip: a committee line can never land between
    two general ones. The general lines here are given higher positions than the committee
    line on purpose, so the test fails if the ordering is ever reduced to ``position``
    alone.
    """
    other_committee = factory.committee("UNSC")
    factory.broadcast(body="general late", position=9)
    factory.broadcast(body="general early", position=1)
    factory.broadcast(body="committee line", committee=committee, position=0)
    factory.broadcast(body="other committee line", committee=other_committee)

    payload = domain.get_delegate_dashboard(db, delegate.account_id)

    assert payload.announcements == ["general early", "general late", "committee line"]


def test_lines_outside_their_schedule_window_are_hidden(db, factory, delegate):
    """A line that has ended, or has not started, is not shown.

    NULL means "always": no ``starts_at`` is live immediately, no ``ends_at`` never
    expires. The live row asserts that, and the two neighbours assert the boundaries are
    exclusive rather than merely "roughly now".
    """
    factory.broadcast(body="already over", ends_at=utcnow() - timedelta(seconds=1))
    factory.broadcast(body="not started", starts_at=utcnow() + timedelta(seconds=1))
    factory.broadcast(
        body="live",
        starts_at=utcnow() - timedelta(days=1),
        ends_at=utcnow() + timedelta(days=1),
    )

    payload = domain.get_delegate_dashboard(db, delegate.account_id)

    assert payload.announcements == ["live"]


def test_links_are_a_separate_strip_and_a_missing_url_becomes_empty(
    db, factory, delegate
):
    """Announcements and links are two different strips fed from one table.

    A link with no url still renders as a line, so ``url`` is normalised to ``""`` here
    rather than being ``None`` in the payload - the frontend binds it to an href.
    """
    factory.broadcast(kind="link", body="Handbook", url="https://example.test/hb")
    factory.broadcast(kind="link", body="Pending url")
    factory.broadcast(kind="announcement", body="A notice")

    payload = domain.get_delegate_dashboard(db, delegate.account_id)

    assert [(link.text, link.url) for link in payload.conferenceLinks] == [
        ("Handbook", "https://example.test/hb"),
        ("Pending url", ""),
    ]
    assert payload.announcements == ["A notice"]


# --- the position-paper panel ----------------------------------------------------------


def test_an_unsubmitted_paper_reports_empty_text_fields(db, delegate):
    """The panel is always present; the text fields are empty until there is content.

    ``score`` is deliberately ``""`` rather than ``None`` or ``0``: the dashboard renders it
    as a string beside "Score", and a missing grade must not look like a zero.
    """
    paper = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper

    assert paper.status == "unsubmitted"
    assert paper.score == ""
    assert paper.feedback == ""
    assert paper.criteria == []
    assert paper.instructions == []


def test_a_graded_paper_joins_stored_marks_with_the_rubric(db, delegate, monkeypatch):
    """The breakdown is rubric labels joined with the chair's stored marks.

    Three things are pinned at once:

    * JSONB object keys are strings, so ``{"1": 7}`` has to match a rubric id of the
      integer ``1`` **and** ``{"2": 5.0}`` has to match the string ``"2"``. Both directions
      are exercised.
    * a criterion the chair left unmarked is omitted, not reported as a zero;
    * scores come back as floats, because ``maxScore`` is a number in the contract.
    """
    monkeypatch.setattr(
        controls,
        "paper_rubric_data",
        [
            {"id": 1, "label": "Clarity", "maxScore": 10},
            {"id": "2", "label": "Evidence", "maxScore": 5},
            {"id": 3, "label": "Never marked", "maxScore": 5},
        ],
    )
    delegate.paper_status = "graded"
    delegate.paper_grade = "12/15"
    delegate.paper_comments = "Clear and well sourced."
    delegate.paper_rubric_grade = {"1": 7, "2": 5.0}
    db.commit()

    paper = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper

    assert paper.score == "12/15"
    assert paper.feedback == "Clear and well sourced."
    assert [(c.id, c.label, c.score, c.maxScore) for c in paper.criteria] == [
        (1, "Clarity", 7.0, 10.0),
        ("2", "Evidence", 5.0, 5.0),
    ]


def test_marks_are_hidden_until_the_paper_is_graded(db, delegate, monkeypatch):
    """A chair may have started marking; unpublished marks must not leak.

    The gate is the status, not the presence of marks - so a paper that is merely
    ``submitted`` shows an empty breakdown even when ``paper_rubric_grade`` is populated.
    """
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": 1, "label": "Clarity", "maxScore": 10}]
    )
    delegate.paper_status = "submitted"
    delegate.paper_rubric_grade = {"1": 8}
    db.commit()

    paper = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper

    assert paper.status == "submitted"
    assert paper.criteria == []


def test_a_graded_paper_with_no_marks_has_no_breakdown(db, delegate, monkeypatch):
    """``graded`` with an empty marks map is a legal state and must not raise.

    It is what a chair who graded by comment only leaves behind.
    """
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": 1, "label": "Clarity", "maxScore": 10}]
    )
    delegate.paper_status = "graded"
    db.commit()

    paper = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper

    assert paper.status == "graded"
    assert paper.criteria == []


def test_a_criterion_without_a_label_falls_back_to_its_id(db, delegate, monkeypatch):
    """A rubric entry may omit its label; the id stands in rather than rendering blank."""
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": 7, "maxScore": 4}]
    )
    delegate.paper_status = "graded"
    delegate.paper_rubric_grade = {"7": 3}
    db.commit()

    criteria = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper.criteria

    assert [(c.id, c.label) for c in criteria] == [(7, "7")]


def test_marks_for_criteria_that_left_the_rubric_are_ignored(db, delegate, monkeypatch):
    """Stored marks are the outer loop's input, the rubric is the source of truth.

    A criterion deleted from the rubric after it was marked must not resurface from the
    JSONB blob.
    """
    monkeypatch.setattr(
        controls, "paper_rubric_data", [{"id": 1, "label": "Clarity", "maxScore": 10}]
    )
    delegate.paper_status = "graded"
    delegate.paper_rubric_grade = {"1": 6, "99": 4}
    db.commit()

    criteria = domain.get_delegate_dashboard(db, delegate.account_id).positionPaper.criteria

    assert [c.id for c in criteria] == [1]
