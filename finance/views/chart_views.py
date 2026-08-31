"""Chart data views for finance app."""

import datetime
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)


@login_required
def chart_data(request, data_type, object_id):
    """Return chart data for accounts or holdings."""
    try:
        if data_type == "investment_account":
            return _get_investment_account_chart_data(request, object_id)
        elif data_type == "saving_account":
            return _get_saving_account_chart_data(request, object_id)
        elif data_type == "holding":
            return _get_holding_chart_data(request, object_id)
        else:
            return JsonResponse(
                {"success": False, "error": _("Invalid data type")}, status=400
            )
    except Exception as e:
        if settings.DEBUG:
            error_message = str(e)
        else:
            error_message = _("An error occurred while loading chart data")
        return JsonResponse({"success": False, "error": error_message}, status=500)


def _get_investment_account_chart_data(request, account_id):
    """Get chart data for an investment account.

    All series (holdings + cash) are aligned to the same set of dates with
    forward-filled values so the stacked area chart renders correctly.
    """
    account = get_object_or_404(InvestmentAccount, id=account_id)

    holdings = list(InvestmentAccountHolding.objects.filter(account=account))
    holding_histories = list(
        InvestmentAccountHoldingHistory.objects.filter(
            holding__account=account
        ).order_by("valuation_date")
    )

    # Group histories by holding (already sorted by valuation_date)
    holding_hist_by_id: dict[int, list] = defaultdict(list)
    for history in holding_histories:
        holding_hist_by_id[history.holding_id].append(history)  # type: ignore[attr-defined]

    # Cash entries for forward-fill
    cash_entries = list(account.cash_values.order_by("value_date"))

    # Deposits — fetched early so deposit dates are included in all_dates,
    # ensuring every chart in the group shares the same x-axis points.
    deposits = list(
        InvestmentAccountDeposit.objects.filter(account=account).order_by(
            "deposit_date"
        )
    )

    # Collect all unique dates from holdings, histories, cash entries and deposits
    all_dates_set: set[datetime.date] = set()
    for holding in holdings:
        all_dates_set.add(holding.initial_valuation_date)
    for history in holding_histories:
        all_dates_set.add(history.valuation_date.date())
    for cash in cash_entries:
        all_dates_set.add(cash.value_date)
    for deposit in deposits:
        all_dates_set.add(deposit.deposit_date)
    all_dates = sorted(all_dates_set)

    # Build per-holding forward-filled series aligned to all_dates
    holdings_series: list[dict] = []
    total_by_date: dict[str, float] = {d.isoformat(): 0.0 for d in all_dates}

    for holding in holdings:
        holding_data: list[dict] = []
        hist_list = holding_hist_by_id.get(holding.id, [])
        hist_idx = 0
        current_value = float(holding.initial_value.amount)
        for d in all_dates:
            if d < holding.initial_valuation_date:
                continue
            while (
                hist_idx < len(hist_list)
                and hist_list[hist_idx].valuation_date.date() <= d
            ):
                current_value = float(hist_list[hist_idx].value.amount)
                hist_idx += 1
            date_str = d.isoformat()
            holding_data.append({"date": date_str, "value": current_value})
            total_by_date[date_str] += current_value
        if holding_data:
            holdings_series.append({"name": holding.short_name, "data": holding_data})

    # Build cash series (forward-filled) and add to totals
    cash_data: list[dict] = []
    cash_idx = 0
    current_cash = float(account.opening_cash_value.amount)
    for d in all_dates:
        while cash_idx < len(cash_entries) and cash_entries[cash_idx].value_date <= d:
            current_cash = float(cash_entries[cash_idx].value.amount)
            cash_idx += 1
        date_str = d.isoformat()
        cash_data.append({"date": date_str, "value": current_cash})
        total_by_date[date_str] += current_cash
    holdings_series.append({"name": str(_("Cash")), "data": cash_data})

    # Build total values (holdings + cash at each date)
    history_data = [
        {"date": date_str, "value": total}
        for date_str, total in sorted(total_by_date.items())
    ]

    # Get deposit amounts for the account
    deposits_data = [
        {
            "date": deposit.deposit_date.isoformat(),
            "value": float(deposit.amount.amount),
        }
        for deposit in deposits
    ]

    # Cumulative invested capital: initial holding values + deposits accumulated over time
    investment_events = [
        (
            holding.initial_valuation_date.isoformat(),
            float(holding.initial_value.amount),
        )
        for holding in holdings
    ]
    for deposit in deposits:
        investment_events.append(
            (deposit.deposit_date.isoformat(), float(deposit.amount.amount))
        )
    invested_data = _build_invested_data(
        investment_events, {d.isoformat() for d in all_dates}
    )

    return JsonResponse(
        {
            "success": True,
            "name": str(account),
            "values": history_data,
            "deposits": deposits_data,
            "invested": invested_data,
            "holdings_series": holdings_series,
        }
    )


def _build_invested_data(
    investment_events: list[tuple[str, float]], all_dates: set[str]
) -> list[dict]:
    """Build cumulative invested capital data from events and known dates."""
    investment_events.sort(key=lambda x: x[0])
    all_invested_dates = set(all_dates)
    for event_date, __ in investment_events:
        all_invested_dates.add(event_date)
    invested_data = []
    event_idx = 0
    running_total = 0.0
    for date_str in sorted(all_invested_dates):
        while (
            event_idx < len(investment_events)
            and investment_events[event_idx][0] <= date_str
        ):
            running_total += investment_events[event_idx][1]
            event_idx += 1
        invested_data.append({"date": date_str, "value": running_total})
    return invested_data


def _get_saving_account_chart_data(request, account_id):
    """Get chart data for a saving account."""
    account = get_object_or_404(SavingAccount, id=account_id)

    # Get account history
    history_data = [
        {
            "date": account.opening_date.isoformat(),
            "value": float(account.opening_value.amount),
        }
    ]

    for entry in SavingAccountValue.objects.filter(account=account).order_by(
        "value_date"
    ):
        history_data.append(
            {
                "date": entry.value_date.isoformat(),
                "value": float(entry.value.amount),
            }
        )

    # Get deposit amounts for the account
    deposits_data = []
    deposits = list(
        SavingAccountDeposit.objects.filter(account=account).order_by("deposit_date")
    )
    for deposit in deposits:
        deposits_data.append(
            {
                "date": deposit.deposit_date.isoformat(),
                "value": float(deposit.amount.amount),
            }
        )

    # Cumulative invested capital: opening value + deposits accumulated over time
    # Use the union of history dates and event dates so deposits/withdrawals
    # always create a step even when there is no value snapshot on that day.
    investment_events = [
        (account.opening_date.isoformat(), float(account.opening_value.amount))
    ]
    for deposit in deposits:
        investment_events.append(
            (deposit.deposit_date.isoformat(), float(deposit.amount.amount))
        )
    invested_data = _build_invested_data(
        investment_events, {str(item["date"]) for item in history_data}
    )

    return JsonResponse(
        {
            "success": True,
            "name": str(account),
            "values": history_data,
            "deposits": deposits_data,
            "invested": invested_data,
        }
    )


def _get_holding_chart_data(request, holding_id):
    """Get chart data for a holding."""
    holding = get_object_or_404(InvestmentAccountHolding, id=holding_id)

    # Get holding history
    history_data = [
        {
            "date": holding.initial_valuation_date.isoformat(),
            "value": float(holding.initial_value.amount),
        }
    ]
    quantity_data = []
    if holding.initial_quantity:
        quantity_data.append(
            {
                "date": holding.initial_valuation_date.isoformat(),
                "quantity": float(holding.initial_quantity),
            }
        )
    holding_history = InvestmentAccountHoldingHistory.objects.filter(
        holding=holding
    ).order_by("valuation_date")

    for entry in holding_history:
        if entry.quantity:
            quantity_data.append(
                {
                    "date": entry.valuation_date.date().isoformat(),
                    "quantity": float(entry.quantity),
                }
            )
        history_data.append(
            {
                "date": entry.valuation_date.date().isoformat(),
                "value": float(entry.value.amount),
            }
        )

    return JsonResponse(
        {
            "success": True,
            "name": str(holding),
            "values": history_data,
            "quantities": quantity_data,
        }
    )
