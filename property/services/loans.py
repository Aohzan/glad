"""Loan figures shared by the property pages, all derived from the loan schedules."""

import datetime
from collections.abc import Iterable

from django.db.models import QuerySet

from property.models import Property, PropertyLedgerEntry, PropertyLoan
from property.utils import LoanCosts

#: Ledger categories of the loan costs, which the loan schedules already count.
LOAN_LEDGER_CATEGORIES = (
    PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
    PropertyLedgerEntry.ManagementCategory.LOAN_INSURANCE,
    PropertyLedgerEntry.ManagementCategory.LOAN_REPAYMENT,
)


def without_loan_entries(
    entries: QuerySet[PropertyLedgerEntry], property_obj: Property
) -> QuerySet[PropertyLedgerEntry]:
    """Leave out the ledger entries the loans of *property_obj* already count.

    The loan schedules are the source of the loan costs: once a property has a
    loan, ledger entries recording its interest, insurance or repayment (for
    instance the bank's yearly interest statement, kept for the LMNP return)
    would count them twice in the cash flow. Without a loan, they are the only
    record of those costs and stay.
    """
    if property_obj.loans.exists():
        return entries.exclude(management_category__in=LOAN_LEDGER_CATEGORIES)
    return entries


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
