"""All loans dashboard view: aggregated view of every property loan."""

import csv
import datetime
import json
from decimal import Decimal

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from moneyed import Money

from property.models import PropertyLoan
from property.utils import build_loan_monthly_maps


def _loan_label(loan: PropertyLoan) -> str:
    """Return a human-readable label for a loan, prefixed by its property."""
    loan_name = loan.name or loan.lender or f"#{loan.pk}"
    return f"{loan.property.name} — {loan_name}"


def _build_loans_with_totals(loans: list[PropertyLoan]) -> list[dict]:
    """Build loan detail rows (property, duration, totals, remaining) for all loans."""
    result = []
    for loan in loans:
        duration = loan.get_duration_months()
        if loan.monthly_payment is not None and duration > 0:
            monthly = loan.monthly_payment.amount
            insurance = (
                loan.insurance.amount if loan.insurance is not None else Decimal("0")
            )
            total_repaid = Money(
                (monthly + insurance) * duration, loan.original_amount.currency
            )
        else:
            total_repaid = None

        total_cost = (
            total_repaid.amount - loan.original_amount.amount
            if total_repaid is not None
            else None
        )

        result.append(
            {
                "property": loan.property,
                "loan": loan,
                "duration_months": duration,
                "total_repaid": total_repaid,
                "total_cost": total_cost,
                "remaining_balance": loan.remaining_balance(),
                "capital_paid": loan.amount_paid(),
                "interest_paid": loan.interest_paid_to_date(),
                "insurance_paid": loan.insurance_paid_to_date(),
            }
        )
    return result


def _build_all_loans_chart_data(loans: list[PropertyLoan]) -> dict:
    """Build per-loan monthly chart data across all properties.

    Same shape as the per-property loans panel chart:
    - loans: list of {name, data: [{x, y}]} — total payment per month per loan
    - total_capital: [{x, y}] — total capital repaid per month across all loans
    - total_interest: [{x, y}] — total interest paid per month across all loans
    """
    loan_series: list[dict] = []
    all_capital: dict[tuple[int, int], Decimal] = {}
    all_interest: dict[tuple[int, int], Decimal] = {}

    for loan in loans:
        if loan.start_date is None or loan.end_date is None:
            continue

        capital_map: dict[tuple[int, int], Decimal] = {}
        interest_map: dict[tuple[int, int], Decimal] = {}
        insurance_map: dict[tuple[int, int], Decimal] = {}

        if loan.amortization_entries.exists():
            for entry in loan.amortization_entries.all():
                key = (entry.date.year, entry.date.month)
                capital_map[key] = (
                    capital_map.get(key, Decimal("0")) + entry.capital.amount
                )
                interest_map[key] = (
                    interest_map.get(key, Decimal("0")) + entry.interest.amount
                )
        elif loan.monthly_payment is not None and loan.interest_rate is not None:
            insurance_amount = loan.insurance.amount if loan.insurance else Decimal("0")
            interest_map, capital_map, insurance_map = build_loan_monthly_maps(
                start_date=loan.start_date,
                end_date=loan.end_date,
                original_amount=loan.original_amount.amount,
                monthly_payment=loan.monthly_payment.amount,
                interest_rate=loan.interest_rate,
                insurance_amount=insurance_amount,
                disbursement_date=loan.start_date,
                first_payment_date=loan.first_payment_date,
            )
        else:
            continue

        all_months = set(capital_map) | set(interest_map) | set(insurance_map)
        total_map: dict[tuple[int, int], Decimal] = {}
        for key in all_months:
            total = (
                capital_map.get(key, Decimal("0"))
                + interest_map.get(key, Decimal("0"))
                + insurance_map.get(key, Decimal("0"))
            )
            total_map[key] = total
            all_capital[key] = all_capital.get(key, Decimal("0")) + capital_map.get(
                key, Decimal("0")
            )
            all_interest[key] = all_interest.get(key, Decimal("0")) + interest_map.get(
                key, Decimal("0")
            )

        sorted_months = sorted(total_map.keys())
        loan_series.append(
            {
                "name": _loan_label(loan),
                "data": [
                    {"x": f"{y}-{m:02d}-01", "y": float(total_map[(y, m)])}
                    for y, m in sorted_months
                ],
            }
        )

    all_months_sorted = sorted(set(all_capital) | set(all_interest))
    total_capital_series = [
        {"x": f"{y}-{m:02d}-01", "y": float(all_capital.get((y, m), Decimal("0")))}
        for y, m in all_months_sorted
    ]
    total_interest_series = [
        {"x": f"{y}-{m:02d}-01", "y": float(all_interest.get((y, m), Decimal("0")))}
        for y, m in all_months_sorted
    ]

    return {
        "loans": loan_series,
        "total_capital": total_capital_series,
        "total_interest": total_interest_series,
    }


def _compute_summary(loans_with_totals: list[dict]) -> dict:
    """Compute aggregate summary metrics across all loans.

    Loans in a currency different from the first encountered are skipped from
    the totals to keep the aggregation consistent (multi-currency portfolios
    are not expected in practice).
    """
    today = datetime.date.today()
    currency: str | None = None
    total_mensuality = Decimal("0")
    total_capital_paid = Decimal("0")
    total_interest_paid = Decimal("0")
    total_insurance_paid = Decimal("0")
    total_remaining = Decimal("0")

    for item in loans_with_totals:
        loan = item["loan"]
        loan_currency = str(loan.original_amount.currency)
        if currency is None:
            currency = loan_currency
        elif loan_currency != currency:
            continue

        total_capital_paid += item["capital_paid"].amount
        total_interest_paid += item["interest_paid"].amount
        total_insurance_paid += item["insurance_paid"].amount
        total_remaining += item["remaining_balance"].amount

        is_active = loan.start_date <= today and (
            loan.end_date is None or today < loan.end_date
        )
        if is_active and loan.monthly_payment is not None:
            insurance = (
                loan.insurance.amount if loan.insurance is not None else Decimal("0")
            )
            total_mensuality += loan.monthly_payment.amount + insurance

    currency = currency or "EUR"
    return {
        "total_mensuality": Money(total_mensuality, currency),
        "total_capital_paid": Money(total_capital_paid, currency),
        "total_interest_paid": Money(total_interest_paid, currency),
        "total_insurance_paid": Money(total_insurance_paid, currency),
        "total_remaining": Money(total_remaining, currency),
    }


def _export_loans_csv(loans_with_totals: list[dict]) -> HttpResponse:
    """Build a CSV export response for the given loan rows."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="loans_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "property",
            "loan_name",
            "lender",
            "start_date",
            "end_date",
            "original_amount",
            "monthly_payment",
            "insurance",
            "interest_rate",
            "duration_months",
            "capital_paid",
            "interest_paid",
            "insurance_paid",
            "total_cost",
            "remaining_balance",
        ]
    )
    for item in loans_with_totals:
        loan = item["loan"]
        writer.writerow(
            [
                loan.property.name,
                loan.name or "",
                loan.lender or "",
                loan.start_date.isoformat() if loan.start_date else "",
                loan.end_date.isoformat() if loan.end_date else "",
                loan.original_amount.amount,
                loan.monthly_payment.amount if loan.monthly_payment else "",
                loan.insurance.amount if loan.insurance else "",
                loan.interest_rate,
                item["duration_months"],
                item["capital_paid"].amount,
                item["interest_paid"].amount,
                item["insurance_paid"].amount,
                item["total_cost"] if item["total_cost"] is not None else "",
                item["remaining_balance"].amount,
            ]
        )
    return response


def all_loans_view(request: HttpRequest) -> HttpResponse:
    """Dashboard view listing all current loans across every property."""
    loans = list(
        PropertyLoan.objects.select_related("property")
        .prefetch_related("amortization_entries")
        .order_by("property__name", "start_date")
    )

    loans_with_totals = _build_loans_with_totals(loans)

    if request.GET.get("format") == "csv":
        return _export_loans_csv(loans_with_totals)

    chart_data = _build_all_loans_chart_data(loans)
    summary = _compute_summary(loans_with_totals)

    context = {
        "loans_with_totals": loans_with_totals,
        "loan_chart_data_json": json.dumps(chart_data),
        "summary": summary,
        "today": datetime.date.today(),
    }
    return render(request, "property/all_loans.html", context)
