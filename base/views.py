"""Base views for the Django application."""

import datetime
from collections import defaultdict
from typing import Any

from django.contrib import messages
from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from glad.settings import DEFAULT_CURRENCY
from property.models import Property


def get_object_or_redirect(
    request: HttpRequest,
    model: type[models.Model],
    pk: int,
    error_message: str,
    redirect_url: str,
    redirect_kwargs: dict[str, Any] | None = None,
    **filter_kwargs: Any,
) -> tuple[models.Model | None, HttpResponse | None]:
    """Retrieve a model instance or redirect with an error message.

    Returns ``(obj, None)`` on success and ``(None, redirect_response)`` when
    the object is not found.  Any extra *filter_kwargs* are passed directly to
    the ORM ``filter()`` call alongside the ``pk`` lookup so callers can scope
    the query (e.g. ``property=property_obj``).  *redirect_kwargs* are forwarded
    to ``redirect()`` as keyword arguments (e.g. ``{"pk": property_pk}``).
    """
    obj = model.objects.filter(pk=pk, **filter_kwargs).first()
    if obj is not None:
        return obj, None
    messages.error(request, error_message)
    return None, redirect(redirect_url, **(redirect_kwargs or {}))


# Helper function to convert datetime to date if needed
def safe_date_compare(date_obj, datetime_obj):
    """
    Safely compare a date and datetime object by converting datetime to date.
    This avoids the '<' not supported between instances of 'datetime.date' and 'datetime.datetime' error.
    """
    if isinstance(date_obj, datetime.datetime) and isinstance(
        datetime_obj, datetime.date
    ):
        return date_obj.date() <= datetime_obj
    elif isinstance(date_obj, datetime.date) and isinstance(
        datetime_obj, datetime.datetime
    ):
        return date_obj <= datetime_obj.date()
    else:
        return date_obj <= datetime_obj


class IndexView(TemplateView):
    """View for the index page."""

    template_name = "index.html"

    def get(self, request, *args, **kwargs):
        # Get total values of saving accounts grouped by currency
        saving_accounts = SavingAccount.objects.filter(is_active=True)
        saving_account_by_currency = defaultdict(list)
        for account in saving_accounts:
            saving_account_by_currency[account.currency].append(account)
        total_saving_accounts_by_currency: dict[str, Money] = {}
        for currency, accounts in saving_account_by_currency.items():
            total_saving_accounts_by_currency[currency] = sum(
                (account.get_value() for account in accounts), Money(0, currency)
            )

        # Get total values of investment accounts grouped by currency
        investment_accounts = InvestmentAccount.objects.filter(is_active=True)
        investment_account_by_currency = defaultdict(list)
        for account in investment_accounts:
            investment_account_by_currency[account.currency].append(account)
        total_investment_accounts_by_currency: dict[str, Money] = {}
        for currency, accounts in investment_account_by_currency.items():
            total_investment_accounts_by_currency[currency] = sum(
                (account.current_value for account in accounts), Money(0, currency)
            )

        # Get total value of properties (only include active properties)
        properties = Property.objects.filter(is_active=True)
        properties_by_currency = defaultdict(list)
        for property in properties:
            properties_by_currency[property.currency].append(property)
        # Calculate total value of properties (both net and gross)
        total_properties_net_by_currency: dict[str, Money] = {}
        total_properties_gross_by_currency: dict[str, Money] = {}
        for currency, properties in properties_by_currency.items():
            total_properties_net_by_currency[currency] = sum(
                (property.net_value for property in properties), Money(0, currency)
            )
            total_properties_gross_by_currency[currency] = sum(
                (property.gross_value for property in properties), Money(0, currency)
            )

        # Keep compatibility with existing code
        total_properties_value_by_currency = total_properties_net_by_currency

        # Calculate the total net worth by currency
        net_worth_by_currency = {}
        for currency in set(
            list(total_investment_accounts_by_currency.keys())
            + list(total_saving_accounts_by_currency.keys())
            + list(properties_by_currency.keys())
        ):
            net_worth_by_currency[currency] = Money(0, currency)
            if currency in total_saving_accounts_by_currency:
                net_worth_by_currency[currency] += total_saving_accounts_by_currency[
                    currency
                ]
            if currency in total_investment_accounts_by_currency:
                net_worth_by_currency[currency] += (
                    total_investment_accounts_by_currency[currency]
                )
            if currency in total_properties_value_by_currency:
                net_worth_by_currency[currency] += total_properties_value_by_currency[
                    currency
                ]

        # Calculate global progression (30 days)
        days = 30
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=days)

        # Get current total values - handle each currency separately
        # For display purposes, we'll use the first currency we find
        default_currency = DEFAULT_CURRENCY
        if total_investment_accounts_by_currency:
            default_currency = list(total_investment_accounts_by_currency.keys())[0]
        elif total_saving_accounts_by_currency:
            default_currency = list(total_saving_accounts_by_currency.keys())[0]
        elif total_properties_value_by_currency:
            default_currency = list(total_properties_value_by_currency.keys())[0]

        # Get the main currency values or default to 0
        total_investments = total_investment_accounts_by_currency.get(
            default_currency, Money(0, default_currency)
        )
        total_savings = total_saving_accounts_by_currency.get(
            default_currency, Money(0, default_currency)
        )
        total_properties = total_properties_net_by_currency.get(
            default_currency, Money(0, default_currency)
        )
        total_properties_net = total_properties_net_by_currency.get(
            default_currency, Money(0, default_currency)
        )
        total_properties_gross = total_properties_gross_by_currency.get(
            default_currency, Money(0, default_currency)
        )

        # Calculate total net worth for the main currency
        total_net_worth = total_investments + total_savings + total_properties_net

        # Calculate global progression for the main currency
        global_progression = 0
        try:
            # Get value from 30 days ago for the main currency
            thirty_days_ago = now - datetime.timedelta(days=days)

            # Get all saving accounts that were active at that time
            historical_saving_accounts = list(
                saving_accounts
            )  # Currently active accounts
            # Add accounts that are now closed but were active at that time
            historical_saving_accounts.extend(
                SavingAccount.objects.filter(
                    is_active=False, closing_date__gt=thirty_days_ago.date()
                )
            )

            # Get historical saving account values - handle with try/except
            old_saving_total = Money(0, default_currency)
            for account in historical_saving_accounts:
                if account.currency == default_currency:
                    try:
                        old_saving_total += account.get_value(max_date=thirty_days_ago)
                    except TypeError:
                        # If there's a type error, try with the date component
                        old_saving_total += account.get_value(
                            max_date=thirty_days_ago.date()
                        )
                    except Exception:
                        # If all else fails, use current value
                        old_saving_total += account.get_value()

            # Get all investment accounts that were active at that time
            historical_investment_accounts = list(
                investment_accounts
            )  # Currently active accounts
            # Add accounts that are now closed but were active at that time
            historical_investment_accounts.extend(
                InvestmentAccount.objects.filter(
                    is_active=False, closing_date__gt=thirty_days_ago.date()
                )
            )

            # Get historical investment account values - handle with try/except
            old_investment_total = Money(0, default_currency)
            for account in historical_investment_accounts:
                if account.currency == default_currency:
                    try:
                        old_investment_total += account.get_value(
                            max_date=thirty_days_ago
                        )
                    except TypeError:
                        # If there's a type error, try with the date component
                        old_investment_total += account.get_value(
                            max_date=thirty_days_ago.date()
                        )
                    except Exception:
                        # If all else fails, use current value
                        old_investment_total += account.get_value()

            # Calculate property values from 30 days ago
            old_property_total = Money(0, default_currency)
            # Filter properties to those that existed 30 days ago (purchased before or during that time)
            historical_properties = [
                p for p in properties if p.buying_date <= thirty_days_ago.date()
            ]
            for property_item in historical_properties:
                if property_item.currency == default_currency:
                    try:
                        # Use net value for consistency
                        value = property_item.net_value
                        old_property_total += value
                    except Exception:
                        # If all else fails, skip this property
                        pass

            # Calculate total from 30 days ago
            old_total = (
                old_saving_total.amount
                + old_investment_total.amount
                + old_property_total.amount
            )
            current_total = (
                total_savings.amount
                + total_investments.amount
                + total_properties_net.amount
            )

            if old_total > 0:
                global_progression = round(
                    ((current_total - old_total) / old_total) * 100, 2
                )
        except Exception:
            # In case of error, default to 0
            global_progression = 0

        # Get patrimony evolution data (for 24 months to allow "All" view)
        patrimony_months = []
        patrimony_evolution_investments = []
        patrimony_evolution_savings = []
        patrimony_evolution_properties_net = []
        patrimony_evolution_properties_gross = []

        # Generate data for the last 24 months to allow for longer history
        for i in range(24, -1, -1):
            # Use proper monthly calculation instead of 30-day approximation
            year = now.year
            month = now.month - i

            # Handle year rollover
            while month <= 0:
                month += 12
                year -= 1

            # Create first day of the month for consistent calculations
            month_date = datetime.datetime(year, month, 1)
            month_str = month_date.strftime("%b %Y")
            patrimony_months.append(month_str)

            # Get all saving accounts that were active at that month
            month_saving_accounts = list(saving_accounts)  # Currently active accounts
            # Add accounts that are now closed but were active at that time
            month_saving_accounts.extend(
                SavingAccount.objects.filter(
                    is_active=False, closing_date__gt=month_date.date()
                )
            )

            # Get saving account values for this month - handle with try/except
            month_saving_total = 0
            for account in month_saving_accounts:
                if account.currency == default_currency:
                    try:
                        value = account.get_value(max_date=month_date)
                        if value:
                            month_saving_total += value.amount
                    except TypeError:
                        # If there's a type error, try with the date component
                        value = account.get_value(max_date=month_date.date())
                        if value:
                            month_saving_total += value.amount
                    except Exception:
                        # If all else fails, skip this account
                        pass

            # Get all investment accounts that were active at that month
            month_investment_accounts = list(
                investment_accounts
            )  # Currently active accounts
            # Add accounts that are now closed but were active at that time
            month_investment_accounts.extend(
                InvestmentAccount.objects.filter(
                    is_active=False, closing_date__gt=month_date.date()
                )
            )

            # Get investment account values for this month - handle with try/except
            month_investment_total = 0
            for account in month_investment_accounts:
                if account.currency == default_currency:
                    try:
                        value = account.get_value(max_date=month_date)
                        if value:
                            month_investment_total += value.amount
                    except TypeError:
                        # If there's a type error, try with the date component
                        value = account.get_value(max_date=month_date.date())
                        if value:
                            month_investment_total += value.amount
                    except Exception:
                        # If all else fails, skip this account
                        pass

            # Get all properties that were active at that month (purchased before or during that month)
            month_properties = [
                p for p in properties if p.buying_date <= month_date.date()
            ]

            # Get property values for this month
            month_property_net_total = 0
            month_property_gross_total = 0
            for property_item in month_properties:
                if property_item.currency == default_currency:
                    try:
                        # For property net value at this specific month
                        net_value = property_item.net_value_at_date(month_date.date())
                        if net_value:
                            month_property_net_total += net_value.amount

                        # For property gross value at this specific month
                        gross_value = property_item.get_value(max_date=month_date)
                        if gross_value:
                            month_property_gross_total += gross_value.amount
                    except Exception:
                        # If there's an error, skip this property
                        pass

            # Store each category separately
            # Calculate loans amount for this month (gross - net)
            month_property_loans_total = (
                month_property_gross_total - month_property_net_total
            )
            patrimony_evolution_investments.append(float(month_investment_total))
            patrimony_evolution_savings.append(float(month_saving_total))
            patrimony_evolution_properties_net.append(float(month_property_net_total))
            patrimony_evolution_properties_gross.append(
                float(month_property_loans_total)
            )

        # Generate breakdown data for pie chart
        # Properties loans = gross - net (the amount owed on properties)
        total_properties_loans = total_properties_gross - total_properties_net
        breakdown_labels = [
            "Investments",
            "Savings",
            "Properties Net",
            "Properties Loans",
        ]
        breakdown_values = [
            float(total_investments.amount),
            float(total_savings.amount),
            float(total_properties_net.amount),
            float(total_properties_loans.amount),
        ]

        # Generate alerts
        alerts = []
        # Check for accounts with negative progression
        for account in saving_accounts:
            progression = account.get_progression(days)
            if progression.gross_progression < -5:  # Alert if more than 5% decrease
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(progression.gross_progression)}%",
                        "type_css": "danger",
                    }
                )

        for account in investment_accounts:
            progression = account.get_progression(days)
            if progression.gross_progression < -5:  # Alert if more than 5% decrease
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(progression.gross_progression)}%",
                        "type_css": "danger",
                    }
                )

        # Get latest operations
        latest_operations = []

        # Get latest saving account values
        latest_saving_values = SavingAccountValue.objects.all().order_by("-value_date")[
            :5
        ]
        for value in latest_saving_values:
            latest_operations.append(
                {
                    "label": _("Value update: ") + str(value.account),
                    "amount": value.value,
                    "date": value.value_date,
                    "icon": "bi-piggy-bank",
                    "type_css": "success",
                }
            )

        # Get latest investment account cash updates
        latest_investment_cash = InvestmentAccountCash.objects.all().order_by(
            "-value_date"
        )[:5]
        for cash in latest_investment_cash:
            latest_operations.append(
                {
                    "label": _("Cash update: ") + str(cash.account),
                    "amount": cash.value,
                    "date": cash.value_date,
                    "icon": "bi-cash-coin",
                    "type_css": "primary",
                }
            )

        # Get latest holding history
        latest_holdings = InvestmentAccountHoldingHistory.objects.all().order_by(
            "-valuation_date"
        )[:5]
        for holding in latest_holdings:
            latest_operations.append(
                {
                    "label": _("Holding update: ") + str(holding.holding),
                    "amount": holding.value,
                    "date": holding.valuation_date,
                    "icon": "bi-graph-up",
                    "type_css": "info",
                }
            )

        latest_operations = latest_operations[:10]  # Limit to 10 most recent

        # Prepare all accounts for progress bars
        all_accounts = []

        # Add saving accounts
        for account in saving_accounts:
            progression = account.get_progression(days)
            progression_percent = min(max(float(progression.gross_progression), 0), 100)
            progression_css = (
                "success"
                if progression.gross_progression > 0
                else "danger"
                if progression.gross_progression < 0
                else "secondary"
            )

            all_accounts.append(
                {
                    "name": str(account),
                    "progression_percent": progression_percent,
                    "progression_css": progression_css,
                    "icon": "bi-piggy-bank",
                    "owner": account.owner or "",
                }
            )

        # Add investment accounts
        for account in investment_accounts:
            progression = account.get_progression(days)
            progression_percent = min(max(float(progression.gross_progression), 0), 100)
            progression_css = (
                "success"
                if progression.gross_progression > 0
                else "danger"
                if progression.gross_progression < 0
                else "secondary"
            )

            all_accounts.append(
                {
                    "name": str(account),
                    "progression_percent": progression_percent,
                    "progression_css": progression_css,
                    "icon": "bi-graph-up",
                    "owner": account.owner or "",
                }
            )

        context = {
            "total_saving_accounts_by_currency": total_saving_accounts_by_currency,
            "total_investment_accounts_by_currency": total_investment_accounts_by_currency,
            "total_properties_value_by_currency": total_properties_value_by_currency,
            "net_worth_by_currency": net_worth_by_currency,
            "total_investments": total_investments,
            "total_savings": total_savings,
            "total_properties": total_properties,
            "total_properties_net": total_properties_net,
            "total_properties_gross": total_properties_gross,
            "total_net_worth": total_net_worth,
            "global_progression": global_progression,
            "patrimony_months": patrimony_months,
            "patrimony_evolution_investments": patrimony_evolution_investments,
            "patrimony_evolution_savings": patrimony_evolution_savings,
            "patrimony_evolution_properties_net": patrimony_evolution_properties_net,
            "patrimony_evolution_properties_gross": patrimony_evolution_properties_gross,
            "breakdown_labels": breakdown_labels,
            "breakdown_values": breakdown_values,
            "alerts": alerts,
            "latest_operations": latest_operations,
            "all_accounts": all_accounts,
            "properties": properties,
        }
        return render(request, self.template_name, context)


def healthcheck(request):
    """Handle GET requests for health check."""
    return JsonResponse({"status": "OK"}, status=200)
