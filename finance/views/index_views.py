"""Index views for the finance app."""

from django.db.models import QuerySet
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from finance.forms import IndexForm
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
)
from finance.models.saving_account import SavingAccount


def index(request):
    """View for the finance index page."""
    # Get days for progression calculation
    form = IndexForm(request.GET or None)
    days = 30
    active_only = True

    if form.is_valid():
        days = form.cleaned_data["days"]
        active_only = form.cleaned_data["active_only"]

    context = {
        "form": form,
        "days": days,
        "savings_accounts": [],
        "investment_accounts": [],
    }

    # Get accounts
    if active_only:
        saving_accounts: QuerySet[SavingAccount] = SavingAccount.objects.filter(
            is_active=True
        )
        investment_accounts: QuerySet[InvestmentAccount] = (
            InvestmentAccount.objects.filter(is_active=True)
        )
    else:
        saving_accounts: QuerySet[SavingAccount] = SavingAccount.objects.all().order_by(
            "-is_active"
        )
        investment_accounts: QuerySet[InvestmentAccount] = (
            InvestmentAccount.objects.all().order_by("-is_active")
        )

    # Calculate current value and progression for each account
    for account in saving_accounts:
        context["savings_accounts"].append(
            {"model": account, "progression": account.get_progression(days)}
        )

    for account in investment_accounts:
        holdings = InvestmentAccountHolding.objects.filter(
            account=account, is_active=True
        )
        # Calculate current value and progression for each holding
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
        context["investment_accounts"].append(
            {
                "model": account,
                "progression": account.get_progression(days),
                "subentries": subentries,
            }
        )

    return render(request, "finance/index.html", context)
