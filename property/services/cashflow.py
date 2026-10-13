"""Cashflow aggregation service for property financial analysis."""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum


def get_annual_cashflow(property_id: int, year: int) -> dict:
    """
    Return income, expenses, and net cashflow for a property and year.

    Only counts entries with amount_currency='EUR'.
    Does not include loan capital repayment (non-deductible) in expenses
    to distinguish accounting cashflow from fiscal result.
    """
    from property.models import PropertyLedgerEntry

    qs = PropertyLedgerEntry.objects.filter(
        property_id=property_id,
        entry_date__year=year,
        amount_currency="EUR",
    )

    income = qs.filter(flow_type=PropertyLedgerEntry.FlowType.INCOME).aggregate(
        total=Sum("amount")
    )["total"] or Decimal(0)
    expenses = qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE).aggregate(
        total=Sum("amount")
    )["total"] or Decimal(0)

    return {
        "year": year,
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
    }


@dataclass(frozen=True)
class LedgerTotals:
    """Ledger occurrences of a property over a period, summed by category."""

    income: dict[str, Decimal] = field(default_factory=dict)
    expenses: dict[str, Decimal] = field(default_factory=dict)
    #: ``(year, month)`` of the months with collected rent.
    rent_months: set[tuple[int, int]] = field(default_factory=set)


def ledger_totals_by_category(
    property_obj,
    date_from: datetime.date,
    date_to: datetime.date,
) -> LedgerTotals:
    """Ledger income and expenses of *property_obj* from *date_from* to *date_to*.

    Recurring entries are expanded up to *date_to*, future dates included, and
    the loan entries the loan schedules already count are left out (see
    :func:`~property.services.loans.without_loan_entries`). Prefetch
    ``ledger_entries__exceptions`` and ``loans`` to read a list of properties
    without a query per property.
    """
    from property.models import PropertyLedgerEntry
    from property.services.loans import LOAN_LEDGER_CATEGORIES

    entries = property_obj.ledger_entries.all()
    if "ledger_entries" not in getattr(property_obj, "_prefetched_objects_cache", {}):
        entries = entries.prefetch_related("exceptions")
    if property_obj.loans.all():
        entries = [
            entry
            for entry in entries
            if entry.management_category not in LOAN_LEDGER_CATEGORIES
        ]
    totals = LedgerTotals()
    for entry in entries:
        income = entry.flow_type == PropertyLedgerEntry.FlowType.INCOME
        bucket = totals.income if income else totals.expenses
        cat = entry.management_category
        for occ in entry.generate_occurrences(end_date=date_to):
            occ_date: datetime.date = occ["date"]
            if occ_date < date_from or occ_date > date_to:
                continue
            bucket[cat] = bucket.get(cat, Decimal(0)) + occ["amount"].amount
            if cat == PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED:
                totals.rent_months.add((occ_date.year, occ_date.month))
    return totals


def build_balance_sheet(
    property_obj,
    date_from: datetime.date,
    date_to: datetime.date,
) -> dict:
    """
    Build a detailed balance sheet for a property over a date range.

    Returns a dict with:
    - income_rows: list of {label, amount} grouped by management_category
    - expense_rows: list of {label, amount} grouped by management_category
    - loan_rows: list of {label, amount} for interest / principal / insurance
    - total_income: Decimal
    - total_expenses: Decimal  (ledger expenses only)
    - total_loan_costs: Decimal  (interest + principal + insurance)
    - total_loan_interest: Decimal
    - total_loan_principal: Decimal
    - total_loan_insurance: Decimal
    - net_cashflow: Decimal  (income - expenses - loan_costs)
    - net_operating: Decimal  (income - expenses - interest - insurance, excl. principal)
    - months_count: int  (number of months in the range)
    - months_with_rent: int  (months that had rent income)
    - occupancy_rate: Decimal  (0–100)
    - gross_yield_annual: Decimal | None  (annualised income / property value × 100)
    """
    from property.models.ledger import ManagementCategory
    from property.services.loans import loan_costs_between
    from property.utils import iter_month_starts, month_end, month_start

    start_month = month_start(date_from)
    end_month = month_start(date_to)
    end_of_range = month_end(date_to)

    ledger = ledger_totals_by_category(property_obj, date_from, end_of_range)
    months_with_rent = ledger.rent_months

    # ── Loan costs in range ───────────────────────────────────────────────────
    loan_costs = loan_costs_between(property_obj.loans.all(), date_from, end_of_range)
    total_loan_interest = loan_costs.interest
    total_loan_principal = loan_costs.principal
    total_loan_insurance = loan_costs.insurance

    # ── Totals ────────────────────────────────────────────────────────────────
    total_income = sum(ledger.income.values(), Decimal(0))
    total_expenses = sum(ledger.expenses.values(), Decimal(0))
    total_loan_costs = total_loan_interest + total_loan_principal + total_loan_insurance
    net_cashflow = total_income - total_expenses - total_loan_costs
    # Operating result excludes loan principal repayment (non-deductible capital)
    net_operating = (
        total_income - total_expenses - total_loan_interest - total_loan_insurance
    )

    # ── Occupancy ─────────────────────────────────────────────────────────────
    all_months = iter_month_starts(start_month, end_month)
    months_count = len(all_months)
    occupancy_rate = (
        Decimal(len(months_with_rent)) / Decimal(months_count) * Decimal(100)
        if months_count > 0
        else Decimal(0)
    )

    # ── Gross yield (annualised) ──────────────────────────────────────────────
    gross_yield_annual: Decimal | None = None
    property_value = property_obj.get_value()
    if property_value and property_value.amount > 0 and months_count > 0:
        annualised_income = total_income * Decimal(12) / Decimal(months_count)
        gross_yield_annual = (
            annualised_income / property_value.amount * Decimal(100)
        ).quantize(Decimal("0.01"))

    # ── Build sorted row lists ────────────────────────────────────────────────
    def rows(amounts: dict[str, Decimal]) -> list[dict]:
        return sorted(
            (
                {"label": ManagementCategory(cat).label, "amount": amount}
                for cat, amount in amounts.items()
            ),
            key=lambda r: r["label"],
        )

    income_rows = rows(ledger.income)
    expense_rows = rows(ledger.expenses)

    from django.utils.translation import gettext_lazy as _

    loan_rows = []
    if total_loan_interest:
        loan_rows.append(
            {"label": str(_("Loan interest")), "amount": total_loan_interest}
        )
    if total_loan_insurance:
        loan_rows.append(
            {"label": str(_("Loan insurance")), "amount": total_loan_insurance}
        )
    if total_loan_principal:
        loan_rows.append(
            {
                "label": str(_("Loan principal repayment")),
                "amount": total_loan_principal,
            }
        )

    return {
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "loan_rows": loan_rows,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_loan_costs": total_loan_costs,
        "total_loan_interest": total_loan_interest,
        "total_loan_principal": total_loan_principal,
        "total_loan_insurance": total_loan_insurance,
        "net_cashflow": net_cashflow,
        "net_operating": net_operating,
        "months_count": months_count,
        "months_with_rent": len(months_with_rent),
        "occupancy_rate": occupancy_rate,
        "gross_yield_annual": gross_yield_annual,
    }
