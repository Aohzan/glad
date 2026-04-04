"""Chart data views for finance app."""

import datetime

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
    """Get chart data for an investment account."""
    account = get_object_or_404(InvestmentAccount, id=account_id, is_active=True)

    # Group by date and sum values
    date_values: dict[str, float] = {}
    holdings_initial_values = InvestmentAccountHolding.objects.filter(account=account)
    for holding in holdings_initial_values:
        date_str = holding.initial_valuation_date.isoformat()
        if date_str not in date_values:
            date_values[date_str] = 0.0
        date_values[date_str] += float(holding.initial_value.amount)
    holding_histories = InvestmentAccountHoldingHistory.objects.filter(
        holding__account=account
    ).order_by("valuation_date")
    for history in holding_histories:
        date_str = history.valuation_date.date().isoformat()
        if date_str not in date_values:
            date_values[date_str] = 0.0
        date_values[date_str] += float(history.value.amount)

    # Get deposit amounts for the account
    date_deposits: dict[str, float] = {}
    deposits = InvestmentAccountDeposit.objects.filter(account=account).order_by(
        "deposit_date"
    )
    for deposit in deposits:
        deposit_date_str = deposit.deposit_date.isoformat()
        if deposit_date_str not in date_deposits:
            date_deposits[deposit_date_str] = 0.0
        date_deposits[deposit_date_str] += float(deposit.amount.amount)

    # Add cash value for each date
    for date_str, total_value in date_values.items():
        cash_value = account.get_cash_value(datetime.datetime.fromisoformat(date_str))
        total_value += float(cash_value.amount)

    history_data = []
    deposits_data = []
    for date_str, total_value in sorted(date_values.items()):
        history_data.append({"date": date_str, "value": total_value})
    for date_str, total_value in sorted(date_deposits.items()):
        deposits_data.append({"date": date_str, "value": total_value})

    return JsonResponse(
        {
            "success": True,
            "name": str(account),
            "values": history_data,
            "deposits": deposits_data,
        }
    )


def _get_saving_account_chart_data(request, account_id):
    """Get chart data for a saving account."""
    account = get_object_or_404(SavingAccount, id=account_id, is_active=True)

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
    deposits = SavingAccountDeposit.objects.filter(account=account).order_by(
        "deposit_date"
    )
    for deposit in deposits:
        deposits_data.append(
            {
                "date": deposit.deposit_date.isoformat(),
                "value": float(deposit.amount.amount),
            }
        )

    return JsonResponse(
        {
            "success": True,
            "name": str(account),
            "values": history_data,
            "deposits": deposits_data,
        }
    )


def _get_holding_chart_data(request, holding_id):
    """Get chart data for a holding."""
    holding = get_object_or_404(InvestmentAccountHolding, id=holding_id, is_active=True)

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
