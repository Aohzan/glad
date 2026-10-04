"""Tests for the dated values read back as of any date."""

import datetime
from decimal import Decimal

from base.services.timeline import DatedValues

D = datetime.date


def _values():
    return DatedValues(
        [
            (1, D(2024, 1, 10), Decimal(10)),
            (1, D(2024, 2, 10), Decimal(20)),
            (1, D(2024, 2, 10), Decimal(25)),
            (2, D(2024, 1, 1), Decimal(5)),
        ]
    )


def test_last_value_on_or_before_the_date():
    values = _values()
    assert values.at(1, D(2024, 1, 10)) == Decimal(10)
    assert values.at(1, D(2024, 2, 9)) == Decimal(10)
    assert values.at(2, D(2030, 1, 1)) == Decimal(5)


def test_last_row_wins_on_the_same_date():
    assert _values().at(1, D(2024, 2, 10)) == Decimal(25)


def test_none_before_the_first_value_or_without_values():
    values = _values()
    assert values.at(1, D(2024, 1, 9)) is None
    assert values.at(3, D(2024, 1, 1)) is None
