"""Loan figures shared by the property pages, all derived from the loan schedules."""

import datetime
from collections.abc import Iterable

from property.models import PropertyLoan
from property.utils import LoanCosts


def loan_costs_by_month(
    loans: Iterable[PropertyLoan],
) -> dict[tuple[int, int], LoanCosts]:
    """Principal, interest and insurance of *loans* due in each ``(year, month)``."""
    months: dict[tuple[int, int], LoanCosts] = {}
    for loan in loans:
        for key, costs in loan.schedule().by_month().items():
            months[key] = months.get(key, LoanCosts()) + costs
    return months


def loan_costs_between(
    loans: Iterable[PropertyLoan], first_day: datetime.date, last_day: datetime.date
) -> LoanCosts:
    """Principal, interest and insurance of *loans* due from *first_day* to *last_day*."""
    return sum(
        (loan.schedule().paid_between(first_day, last_day) for loan in loans),
        LoanCosts(),
    )
