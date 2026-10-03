"""Index views for the finance app."""

import datetime
import json
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from base.services.ownership import HolderResolver
from finance.forms import IndexForm
from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount
from finance.services.history import investment_values_at, saving_values_at

#: Periods offered for the progression column, in days.
DAY_CHOICES = (7, 30, 90, 365)


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


def _kpi(entries: list[dict], total: Money | None) -> dict | None:
    """Total of *entries* with its change over the period, in its currency."""
    if total is None:
        return None
    change = sum(
        (
            e["progression"].gross_difference.amount
            for e in entries
            if str(e["progression"].gross_difference.currency) == str(total.currency)
        ),
        Decimal(0),
    )
    old = total.amount - change
    return {
        "value": total,
        "change": Money(change, total.currency),
        "change_pct": change / abs(old) * 100 if old else None,
    }


def index(request):
    """View for the finance index page."""
    form = IndexForm(request.GET or None)
    days = 30
    active_only = True

    if form.is_valid():
        days = form.cleaned_data["days"]
        active_only = form.cleaned_data["active_only"]

    # Get accounts
    saving_accounts_qs: QuerySet[SavingAccount] = SavingAccount.objects.select_related(
        "account_type"
    )
    investment_accounts_qs: QuerySet[InvestmentAccount] = (
        InvestmentAccount.objects.select_related("account_type")
    )
    if active_only:
        saving_accounts_qs = saving_accounts_qs.filter(is_active=True)
        investment_accounts_qs = investment_accounts_qs.filter(is_active=True)
    else:
        saving_accounts_qs = saving_accounts_qs.order_by("-is_active")
        investment_accounts_qs = investment_accounts_qs.order_by("-is_active")

    # Build account data with KPI totals
    total_saving_value: Money | None = None
    total_investment_value: Money | None = None

    holders = HolderResolver()
    savings_accounts = []
    for account in saving_accounts_qs:
        val = account.current_value
        if total_saving_value is None:
            total_saving_value = val
        elif str(val.currency) == str(total_saving_value.currency):
            total_saving_value += val
        savings_accounts.append(
            {
                "model": account,
                "progression": account.get_progression(days),
                "holder": holders.label(account),
            }
        )

    investment_accounts = []
    for account in investment_accounts_qs:
        # The related manager sets holding.account without querying it again.
        holdings = account.investmentaccountholding_set.filter(is_active=True)  # ty: ignore[unresolved-attribute]
        val = account.current_value
        if total_investment_value is None:
            total_investment_value = val
        elif str(val.currency) == str(total_investment_value.currency):
            total_investment_value += val
        subentries: list[dict[str, Any]] = [
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
        for entry in subentries:
            entry["weight"] = (
                entry["value"].amount / val.amount * 100 if val.amount else None
            )
        investment_accounts.append(
            {
                "model": account,
                "value": val,
                "progression": account.get_progression(days),
                "subentries": subentries,
                "holder": holders.label(account),
            }
        )

    # Chart data – monthly evolution, one series per account
    chart_months: list[str] = []
    chart_series: list[dict] = []

    saving_list = list(saving_accounts_qs)
    investment_list = list(investment_accounts_qs)
    opening_dates = [
        acc.opening_date
        for acc in [*saving_list, *investment_list]
        if acc.opening_date is not None
    ]
    if opening_dates:
        months = list(_iter_month_starts(min(opening_dates), datetime.date.today()))
        chart_months = [m.strftime("%b %Y") for m in months]
        month_ends = [_month_end(m) for m in months]
        # Bulk-load the histories: get_value() per month would cost several
        # queries per account and per month.
        series_by_account = [
            (saving_list, saving_values_at(saving_list, month_ends)),
            (investment_list, investment_values_at(investment_list, month_ends)),
        ]
        for accounts, values in series_by_account:
            for account in accounts:
                chart_series.append(
                    {
                        "name": str(account),
                        "data": [float(v) for v in values[account.pk]],
                    }
                )

    kpi_inv = float(total_investment_value.amount) if total_investment_value else None
    kpi_sav = float(total_saving_value.amount) if total_saving_value else None
    kpi_currency = (
        str(total_investment_value.currency)
        if total_investment_value
        else (str(total_saving_value.currency) if total_saving_value else "EUR")
    )

    totals = [t for t in (total_investment_value, total_saving_value) if t is not None]
    total_finance = (
        sum(totals[1:], totals[0])
        if totals and len({str(t.currency) for t in totals}) == 1
        else None
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
        "kpi_investments": _kpi(investment_accounts, total_investment_value),
        "kpi_savings": _kpi(savings_accounts, total_saving_value),
        "total_finance": total_finance,
        "account_count": len(investment_accounts) + len(savings_accounts),
        "day_choices": DAY_CHOICES,
        "active_only": active_only,
    }
    return render(request, "finance/index.html", context)
