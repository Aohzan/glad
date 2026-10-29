"""Tests for the helpers of the notification checks."""

import datetime
from unittest.mock import patch

from base.services.deadlines import Deadline
from notifications import checks
from notifications.checks import deadline_check, month_day, short_key, when

TODAY = datetime.date(2026, 10, 28)


def test_when():
    assert when(datetime.date(2026, 11, 7), TODAY) == "On Nov. 7, 2026 (in 10 days)"
    assert when(TODAY, TODAY) == "On Oct. 28, 2026 (today)"
    assert when(datetime.date(2026, 10, 27), TODAY) == "On Oct. 27, 2026 (1 day ago)"


def test_month_day():
    assert month_day("05-20", 2026) == datetime.date(2026, 5, 20)
    assert month_day("02-29", 2026) == datetime.date(2026, 2, 28)
    assert month_day("02-29", 2028) == datetime.date(2028, 2, 29)


def test_short_key_is_stable():
    assert short_key("a", 1) == short_key("a", 1)
    assert short_key("a", 1) != short_key("a", 2)
    assert len(short_key("a")) == 20


def _deadline(days: int, kind: str = "loan_end") -> Deadline:
    return Deadline(
        date=TODAY + datetime.timedelta(days=days),
        title="Flat — Loan",
        detail="End of the loan",
        url="/property/1/",
        icon="landmark",
        today=TODAY,
        kind=kind,
    )


def test_deadline_check_window():
    deadlines = [
        _deadline(-30),
        _deadline(-3),
        _deadline(5),
        _deadline(40),
        _deadline(90),
    ]
    with patch.object(checks, "deadlines_of", return_value=deadlines) as source:
        events = list(deadline_check("loan_end")({"days_before": 60}, TODAY))
    source.assert_called_once_with({"loan_end"}, TODAY)
    assert [e.body for e in events] == [
        "On Oct. 25, 2026 (3 days ago)",
        "On Nov. 2, 2026 (in 5 days)",
        "On Dec. 7, 2026 (in 40 days)",
    ]
    assert [e.level for e in events] == ["warning", "warning", "info"]
    assert events[0].title == "End of the loan — Flat — Loan"
    assert events[0].url == "/property/1/"


def test_deadline_check_with_a_long_tolerance():
    with patch.object(checks, "deadlines_of", return_value=[_deadline(-200)]):
        events = list(
            deadline_check("rent_revision", late_days=365)({"days_before": 30}, TODAY)
        )
    assert len(events) == 1
