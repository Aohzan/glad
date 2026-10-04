"""Loan figures shared by the property pages, all derived from the loan schedules."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import QuerySet
from moneyed import Money

from property.models import (
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
)
from property.utils import Installment, LoanCosts

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


@dataclass(frozen=True)
class LoanRow:
    """A loan and the figures the loan tables show on a given day."""

    loan: PropertyLoan
    #: Rows of the amortization table, empty when the schedule is computed.
    entries: list[PropertyLoanAmortizationEntry]
    duration_months: int
    next_installment: Installment | None
    #: Disbursed and not fully repaid yet.
    is_running: bool
    remaining_balance: Money
    capital_paid: Money
    interest_paid: Money
    insurance_paid: Money
    #: Interest and insurance of every installment.
    total_cost: Money
    #: Capital plus total cost.
    total_repaid: Money

    @property
    def has_table(self) -> bool:
        return bool(self.entries)

    @property
    def monthly_payment(self) -> Money | None:
        """Principal and interest of the next installment (or the stored payment)."""
        if self.next_installment is not None:
            return Money(self.next_installment.payment, self.loan.currency)
        return self.loan.monthly_payment

    @property
    def monthly_insurance(self) -> Money | None:
        if self.next_installment is not None:
            if not self.next_installment.insurance:
                return None
            return Money(self.next_installment.insurance, self.loan.currency)
        return self.loan.insurance


def loan_rows(loans: Iterable[PropertyLoan], today: datetime.date) -> list[LoanRow]:
    """The table rows of *loans* as of *today*.

    Prefetch ``amortization_entries`` (and select ``property``) on *loans* to
    read each loan with a single query.
    """
    rows = []
    for loan in loans:
        schedule = loan.schedule()
        currency = loan.currency
        paid = schedule.paid_to(today)
        cost = schedule.total.interest + schedule.total.insurance
        next_installment = schedule.next_installment(today)
        rows.append(
            LoanRow(
                loan=loan,
                entries=list(loan.amortization_entries.all()),
                duration_months=loan.get_duration_months(),
                next_installment=next_installment,
                is_running=loan.start_date <= today and next_installment is not None,
                remaining_balance=loan.remaining_balance(today),
                capital_paid=loan.amount_paid(today),
                interest_paid=Money(paid.interest, currency),
                insurance_paid=Money(paid.insurance, currency),
                total_cost=Money(cost, currency),
                total_repaid=Money(loan.original_amount.amount + cost, currency),
            )
        )
    return rows


@dataclass(frozen=True)
class LoansSummary:
    """Totals of the loan rows sharing the currency of the first one."""

    total_mensuality: Money
    total_capital_paid: Money
    total_interest_paid: Money
    total_insurance_paid: Money
    total_remaining: Money


def loans_summary(rows: Iterable[LoanRow], default_currency: str) -> LoansSummary:
    """Add up *rows*; loans in another currency than the first are left out.

    The total mensuality adds the next installment (with its insurance) of
    the loans currently being repaid.
    """
    currency: str | None = None
    mensuality = capital = interest = insurance = remaining = Decimal(0)
    for row in rows:
        currency = currency or row.loan.currency
        if row.loan.currency != currency:
            continue
        capital += row.capital_paid.amount
        interest += row.interest_paid.amount
        insurance += row.insurance_paid.amount
        remaining += row.remaining_balance.amount
        if row.is_running and row.next_installment is not None:
            mensuality += row.next_installment.payment + row.next_installment.insurance
    currency = currency or default_currency
    return LoansSummary(
        total_mensuality=Money(mensuality, currency),
        total_capital_paid=Money(capital, currency),
        total_interest_paid=Money(interest, currency),
        total_insurance_paid=Money(insurance, currency),
        total_remaining=Money(remaining, currency),
    )


def _month_x(key: tuple[int, int]) -> str:
    return f"{key[0]}-{key[1]:02d}-01"


def loans_chart_data(
    loans: Iterable[PropertyLoan], default_currency: str, *, with_property=False
) -> dict:
    """Monthly installments of *loans* for the stacked loan chart.

    Returns ``loans`` (one series per loan: principal, interest and insurance
    paid each month), ``total_capital`` and ``total_interest`` (all loans),
    and the ``currency``. Every series covers the same months, the union of
    the months of all loans with zeros where a loan has no installment:
    ApexCharts stacks the bars of a datetime axis by position, not by date.
    """
    by_loan = [(loan, loan.schedule().by_month()) for loan in loans]
    by_loan = [(loan, months) for loan, months in by_loan if months]
    months = sorted({key for _loan, loan_months in by_loan for key in loan_months})
    totals: dict[tuple[int, int], LoanCosts] = {}
    series = []
    names: set[str] = set()
    for loan, loan_months in by_loan:
        name = loan.name or loan.lender or f"#{loan.pk}"
        if with_property:
            name = f"{loan.property.name} — {name}"
        if name in names:
            name = f"{name} #{loan.pk}"
        names.add(name)
        series.append(
            {
                "name": name,
                "data": [
                    {
                        "x": _month_x(key),
                        "y": float(loan_months.get(key, LoanCosts()).total),
                    }
                    for key in months
                ],
            }
        )
        for key, costs in loan_months.items():
            totals[key] = totals.get(key, LoanCosts()) + costs
    return {
        "currency": by_loan[0][0].currency if by_loan else default_currency,
        "loans": series,
        "total_capital": [
            {"x": _month_x(key), "y": float(totals[key].principal)} for key in months
        ],
        "total_interest": [
            {"x": _month_x(key), "y": float(totals[key].interest)} for key in months
        ],
    }
