"""Domain tests for ``core.domain.advisors.get_school_overview``.

Two rules are easy to get wrong here and invisible from the outside:

* the payload renames columns for the frontend contract (``school_name`` → ``name``,
  ``zip_code`` → ``zip``, ``invoiceURL`` → ``invoiceUrl``), and the advisor's name comes from
  the **school** row rather than the account;
* the checklist is a conference-wide label list outer-joined to *this school's* ticks, so a
  missing progress row reads as "not done" and a rival school's tick never leaks in.
"""

import pytest

from core.domain import advisors as domain
from core.domain.errors import SchoolNotFound
from crud.database_schema import ChecklistProgress, ConferenceChecklist
from crud.db import utcnow


def _item(factory, label: str, position: int = 0) -> ConferenceChecklist:
    item = ConferenceChecklist(label=label, position=position)
    factory.db.add(item)
    factory.db.commit()
    return item


def _tick(factory, school, item: ConferenceChecklist, *, completed: bool = True) -> None:
    factory.db.add(
        ChecklistProgress(
            school_id=school.account_id,
            item_id=item.id,
            completed=completed,
            updated_at=utcnow(),
        )
    )
    factory.db.commit()


def test_an_advisor_without_a_school_raises_school_not_found(db, factory):
    account = factory.account(role="advisor", identifier="ADV-NO-SCHOOL")

    with pytest.raises(SchoolNotFound):
        domain.get_school_overview(db, account.id)


def test_the_school_fields_are_renamed_for_the_contract(db, advisor, school):
    """Every field is a rename or a straight copy; a silent omission blanks a page."""
    overview = domain.get_school_overview(db, advisor.id)

    assert overview.school.model_dump() == {
        "name": "Test High School",
        "address": "1 Test Way",
        "city": "Testville",
        "state": "CA",
        "zip": "90000",
        "advisorName": "Advisor Person",
        "advisorEmail": "advisor@example.test",
        "advisorPhone": "555-0100",
        "headDelegateName": "Head Delegate",
        "headDelegateEmail": "head@example.test",
        "headDelegatePhone": "555-0101",
    }


def test_the_advisor_name_comes_from_the_school_row_not_the_account(
    db, advisor, school
):
    """Renaming the account must not silently rename the advisor on the school page.

    The two can diverge (an admin edits the school, the account is older), and the page is
    about the school.
    """
    advisor.name = "Renamed Account Person"
    db.commit()

    overview = domain.get_school_overview(db, advisor.id)

    assert overview.school.advisorName == "Advisor Person"


def test_an_absent_invoice_url_becomes_an_empty_string(db, advisor, school):
    """The column is nullable; the payload is not, because it is bound to an href."""
    school.invoiceURL = None
    db.commit()

    assert domain.get_school_overview(db, advisor.id).billing.invoiceUrl == ""


def test_the_invoice_url_and_payment_status_are_passed_through(db, advisor, school):
    school.invoiceURL = "https://example.test/invoice.pdf"
    school.payment_status = "partially paid"
    db.commit()

    billing = domain.get_school_overview(db, advisor.id).billing

    assert billing.invoiceUrl == "https://example.test/invoice.pdf"
    assert billing.paymentStatus == "partially paid"


def test_the_checklist_is_ordered_by_position_then_id(db, factory, advisor, school):
    """Equal positions fall back to ``id``, so the order is stable between requests."""
    _item(factory, "Third", position=9)
    _item(factory, "First", position=1)
    _item(factory, "Second", position=5)

    labels = [entry.label for entry in domain.get_school_overview(db, advisor.id).checklist]

    assert labels == ["First", "Second", "Third"]


def test_items_with_equal_positions_keep_insertion_order(
    db, factory, advisor, school
):
    """The ``id`` tie-break, exercised on its own."""
    _item(factory, "Alpha", position=3)
    _item(factory, "Beta", position=3)

    labels = [entry.label for entry in domain.get_school_overview(db, advisor.id).checklist]

    assert labels == ["Alpha", "Beta"]


def test_a_missing_progress_row_reads_as_not_done(db, factory, advisor, school):
    """The progress table only holds ticks; absence is the normal "not done" state."""
    _item(factory, "Pay the conference fee")

    checklist = domain.get_school_overview(db, advisor.id).checklist

    assert [(entry.label, entry.completed) for entry in checklist] == [
        ("Pay the conference fee", False)
    ]


def test_ticks_are_scoped_to_the_advisors_school(db, factory, advisor, school):
    """A rival's tick on one line and this school's tick on another must not cross."""
    fee = _item(factory, "Pay the conference fee", position=1)
    travel = _item(factory, "Book travel", position=2)
    _tick(factory, school, fee)

    rival = factory.account(role="advisor", identifier="ADV-RIVAL")
    rival_school = factory.school(rival, name="Rival High School")
    _tick(factory, rival_school, travel)

    checklist = domain.get_school_overview(db, advisor.id).checklist

    assert [(entry.label, entry.completed) for entry in checklist] == [
        ("Pay the conference fee", True),
        ("Book travel", False),
    ]


def test_a_stored_false_is_the_same_as_no_row(db, factory, advisor, school):
    """An explicitly cleared box is a ``False`` row; both must read as not done."""
    fee = _item(factory, "Pay the conference fee")
    _tick(factory, school, fee, completed=False)

    checklist = domain.get_school_overview(db, advisor.id).checklist

    assert [(entry.label, entry.completed) for entry in checklist] == [
        ("Pay the conference fee", False)
    ]


def test_every_tick_for_the_school_is_applied(db, factory, advisor, school):
    """More than one level, so a wrong join condition cannot hide behind a single row."""
    first = _item(factory, "Pay the conference fee", position=1)
    second = _item(factory, "Book travel", position=2)
    _tick(factory, school, first)
    _tick(factory, school, second)

    checklist = domain.get_school_overview(db, advisor.id).checklist

    assert [entry.completed for entry in checklist] == [True, True]


def test_no_checklist_lines_is_an_empty_list(db, advisor, school):
    """Before an admin writes the checklist the panel renders nothing rather than failing."""
    assert domain.get_school_overview(db, advisor.id).checklist == []
