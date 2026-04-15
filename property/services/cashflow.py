"""Cashflow aggregation service for property financial analysis."""

import datetime
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
    )["total"] or Decimal("0")
    expenses = qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")

    return {
        "year": year,
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
    }


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
    from property.models import PropertyLedgerEntry, PropertyLoan
    from property.utils import (
        build_loan_monthly_maps,
        iter_month_starts,
        month_end,
        month_start,
    )

    start_month = month_start(date_from)
    end_month = month_start(date_to)
    end_of_range = month_end(date_to)

    # ── Ledger entries in range ───────────────────────────────────────────────
    entries_qs = PropertyLedgerEntry.objects.filter(property=property_obj)

    # Aggregate occurrences by management_category within the date range
    income_by_cat: dict[str, dict] = {}
    expense_by_cat: dict[str, dict] = {}
    months_with_rent: set[tuple[int, int]] = set()

    for entry in entries_qs:
        for occ in entry.generate_occurrences(end_date=end_of_range):
            occ_date: datetime.date = occ["date"]
            if occ_date < date_from or occ_date > end_of_range:
                continue
            amount: Decimal = occ["amount"].amount
            cat = entry.management_category
            cat_label = entry.get_management_category_display()

            if entry.flow_type == PropertyLedgerEntry.FlowType.INCOME:
                if cat not in income_by_cat:
                    income_by_cat[cat] = {"label": cat_label, "amount": Decimal("0")}
                income_by_cat[cat]["amount"] += amount
                if cat == PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED:
                    months_with_rent.add((occ_date.year, occ_date.month))
            else:
                if cat not in expense_by_cat:
                    expense_by_cat[cat] = {"label": cat_label, "amount": Decimal("0")}
                expense_by_cat[cat]["amount"] += amount

    # ── Loan costs in range ───────────────────────────────────────────────────
    loans_qs = PropertyLoan.objects.filter(property=property_obj)
    total_loan_interest = Decimal("0")
    total_loan_principal = Decimal("0")
    total_loan_insurance = Decimal("0")

    for loan in loans_qs:
        insurance_amount = (
            loan.insurance.amount if loan.insurance is not None else Decimal("0")
        )
        interest_map, principal_map, insurance_map = build_loan_monthly_maps(
            start_date=loan.start_date,
            end_date=loan.end_date,
            original_amount=loan.original_amount.amount,
            monthly_payment=loan.monthly_payment.amount
            if loan.monthly_payment
            else Decimal("0"),
            interest_rate=loan.interest_rate,
            insurance_amount=insurance_amount,
        )
        for month in iter_month_starts(start_month, end_month):
            key = (month.year, month.month)
            total_loan_interest += interest_map.get(key, Decimal("0"))
            total_loan_principal += principal_map.get(key, Decimal("0"))
            total_loan_insurance += insurance_map.get(key, Decimal("0"))

    # ── Totals ────────────────────────────────────────────────────────────────
    total_income = sum((v["amount"] for v in income_by_cat.values()), Decimal("0"))
    total_expenses = sum((v["amount"] for v in expense_by_cat.values()), Decimal("0"))
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
        Decimal(len(months_with_rent)) / Decimal(months_count) * Decimal("100")
        if months_count > 0
        else Decimal("0")
    )

    # ── Gross yield (annualised) ──────────────────────────────────────────────
    gross_yield_annual: Decimal | None = None
    property_value = property_obj.get_value()
    if property_value and property_value.amount > 0 and months_count > 0:
        annualised_income = total_income * Decimal("12") / Decimal(months_count)
        gross_yield_annual = (
            annualised_income / property_value.amount * Decimal("100")
        ).quantize(Decimal("0.01"))

    # ── Build sorted row lists ────────────────────────────────────────────────
    income_rows = sorted(income_by_cat.values(), key=lambda r: r["label"])
    expense_rows = sorted(expense_by_cat.values(), key=lambda r: r["label"])

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
