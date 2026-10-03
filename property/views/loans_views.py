"""All loans dashboard view: aggregated view of every property loan."""

import csv
import datetime

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from property.models import PropertyLoan
from property.services.loans import (
    LoanRow,
    loan_rows,
    loans_chart_data,
    loans_summary,
)


def _export_loans_csv(rows: list[LoanRow]) -> HttpResponse:
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
    for row in rows:
        loan = row.loan
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
                row.duration_months,
                row.capital_paid.amount,
                row.interest_paid.amount,
                row.insurance_paid.amount,
                row.total_cost.amount,
                row.remaining_balance.amount,
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

    today = datetime.date.today()
    loans_with_totals = loan_rows(loans, today)

    if request.GET.get("format") == "csv":
        return _export_loans_csv(loans_with_totals)

    summary = loans_summary(loans_with_totals, settings.DEFAULT_CURRENCY)

    context = {
        "loans_with_totals": loans_with_totals,
        "loan_chart_data": loans_chart_data(
            loans, settings.DEFAULT_CURRENCY, with_property=True
        ),
        "summary": summary,
        "today": today,
    }
    return render(request, "property/all_loans.html", context)
