"""Monthly cash flows of a property: rents, charges and loan repayments.

The months of the last year with any activity are kept, and the median of each
flow over them gives a typical month that is not distorted by an exceptional
one (a yearly tax, a vacancy, a large repair).
"""

import datetime
import statistics
from dataclasses import dataclass
from decimal import Decimal

from property.models import Property, PropertyLedgerEntry
from property.services.loans import loan_costs_by_month
from property.utils import LoanCosts, iter_month_starts, month_end, month_start


def occurrences_by_month(
    entries, end_month: datetime.date
) -> dict[tuple[int, int], Decimal]:
    """Aggregate recurring and one-shot entries to month buckets."""
    by_month: dict[tuple[int, int], Decimal] = {}
    end_of_month = month_end(end_month)
    for entry in entries:
        for occurrence in entry.generate_occurrences(end_date=end_of_month):
            key = (occurrence["date"].year, occurrence["date"].month)
            by_month[key] = by_month.get(key, Decimal(0)) + occurrence["amount"].amount
    return by_month


@dataclass(frozen=True)
class MonthlyFlows:
    """Median monthly flows of a property over the last 12 months."""

    rents: Decimal
    charges: Decimal
    loan: Decimal
    cashflow: Decimal


def monthly_flows(
    property_obj: Property, today: datetime.date | None = None
) -> MonthlyFlows:
    """Median income, expenses, loan repayments and cash flow per month.

    Months without any flow are left out; the cash flow median is computed on
    the monthly balances, so it is not the difference of the other medians.
    """
    today = today or datetime.date.today()
    end_month = month_start(today)
    start_month = month_start(datetime.date(today.year - 1, today.month, 1))

    entries_qs = PropertyLedgerEntry.objects.filter(
        property=property_obj
    ).prefetch_related("exceptions")
    revenue_by_month = occurrences_by_month(
        entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.INCOME), end_month
    )
    expense_by_month = occurrences_by_month(
        entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE), end_month
    )
    loan_by_month = loan_costs_by_month(property_obj.loans.all())

    rents, charges, loans, balances = [], [], [], []
    for m in iter_month_starts(start_month, end_month):
        key = (m.year, m.month)
        rev = revenue_by_month.get(key, Decimal(0))
        exp = expense_by_month.get(key, Decimal(0))
        loan = loan_by_month.get(key, LoanCosts()).total
        # Skip months with no financial activity at all (no data)
        if not (rev or exp or loan):
            continue
        rents.append(rev)
        charges.append(exp)
        loans.append(loan)
        balances.append(rev - exp - loan)

    def median(values: list[Decimal]) -> Decimal:
        return Decimal(str(statistics.median(values))) if values else Decimal(0)

    return MonthlyFlows(
        rents=median(rents),
        charges=median(charges),
        loan=median(loans),
        cashflow=median(balances),
    )
