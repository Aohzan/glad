"""Index views for the finance app."""

import datetime
import json

from django.db.models import QuerySet
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from finance.forms import IndexForm
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
)
from finance.models.saving_account import SavingAccount


def _iter_month_starts(start: datetime.date, end: datetime.date):
    """Yield the first day of each month from start to end inclusive."""
    current = start.replace(day=1)
    end_first = end.replace(day=1)
    while current <= end_first:
        yield current
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def _month_end(d: datetime.date) -> datetime.date:
    """Return the last day of the month for the given date."""
    if d.month == 12:
        return d.replace(day=31)
    return d.replace(month=d.month + 1, day=1) - datetime.timedelta(days=1)


def index(request):
    """View for the finance index page."""
    form = IndexForm(request.GET or None)
    days = 30
    active_only = True

    if form.is_valid():
        days = form.cleaned_data["days"]
        active_only = form.cleaned_data["active_only"]

    # Get accounts
    if active_only:
        saving_accounts_qs: QuerySet[SavingAccount] = SavingAccount.objects.filter(
            is_active=True
        )
        investment_accounts_qs: QuerySet[InvestmentAccount] = (
            InvestmentAccount.objects.filter(is_active=True)
        )
    else:
        saving_accounts_qs: QuerySet[SavingAccount] = (
            SavingAccount.objects.all().order_by("-is_active")
        )
        investment_accounts_qs: QuerySet[InvestmentAccount] = (
            InvestmentAccount.objects.all().order_by("-is_active")
        )

    # Build account data with KPI totals
    total_saving_value: Money | None = None
    total_investment_value: Money | None = None

    savings_accounts = []
    for account in saving_accounts_qs:
        val = account.current_value
        if total_saving_value is None:
            total_saving_value = val
        elif str(val.currency) == str(total_saving_value.currency):
            total_saving_value += val
        savings_accounts.append(
            {"model": account, "progression": account.get_progression(days)}
        )

    investment_accounts = []
    for account in investment_accounts_qs:
        holdings = InvestmentAccountHolding.objects.filter(
            account=account, is_active=True
        )
        val = account.current_value
        if total_investment_value is None:
            total_investment_value = val
        elif str(val.currency) == str(total_investment_value.currency):
            total_investment_value += val
        subentries = [
            {
                "id": "cash",
                "name": _("Cash"),
                "value": account.current_cash_value,
                "progression": account.get_cash_progression(days),
            }
        ]
        for holding in holdings:
            subentries.append(
                {
                    "id": holding.id,
                    "name": holding.short_name,
                    "value": holding.value,
                    "progression": holding.get_progression(days),
                }
            )
        investment_accounts.append(
            {
                "model": account,
                "progression": account.get_progression(days),
                "subentries": subentries,
            }
        )

    # Chart data – monthly evolution, one series per account
    chart_months: list[str] = []
    chart_series: list[dict] = []

    all_accounts_for_chart: list[SavingAccount | InvestmentAccount] = list(
        saving_accounts_qs
    ) + list(investment_accounts_qs)
    if all_accounts_for_chart:
        opening_dates = [
            acc.opening_date
            for acc in all_accounts_for_chart
            if acc.opening_date is not None
        ]
        if opening_dates:
            earliest = min(opening_dates)
            today = datetime.date.today()
            months = list(_iter_month_starts(earliest, today))
            chart_months = [m.strftime("%b %Y") for m in months]
            for account in all_accounts_for_chart:
                series_data: list[float | None] = []
                for m in months:
                    me = _month_end(m)
                    try:
                        v = account.get_value(max_date=me)
                        series_data.append(float(v.amount))
                    except Exception:
                        series_data.append(None)
                chart_series.append({"name": str(account), "data": series_data})

    kpi_inv = float(total_investment_value.amount) if total_investment_value else None
    kpi_sav = float(total_saving_value.amount) if total_saving_value else None
    kpi_currency = (
        str(total_investment_value.currency)
        if total_investment_value
        else (str(total_saving_value.currency) if total_saving_value else "EUR")
    )

    context = {
        "form": form,
        "days": days,
        "savings_accounts": savings_accounts,
        "investment_accounts": investment_accounts,
        "total_saving_value": total_saving_value,
        "total_investment_value": total_investment_value,
        "kpi_inv_json": json.dumps(kpi_inv),
        "kpi_sav_json": json.dumps(kpi_sav),
        "kpi_currency_json": json.dumps(kpi_currency),
        "chart_months_json": json.dumps(chart_months),
        "chart_series_json": json.dumps(chart_series),
        "has_chart_data": bool(chart_months),
    }
    return render(request, "finance/index.html", context)
