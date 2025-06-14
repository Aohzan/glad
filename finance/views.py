"""Views for the finance app."""

import logging

from django.db.models import QuerySet
from django.shortcuts import render
from django.views.generic import TemplateView

from finance.forms import IndexForm
from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount

_LOGGER = logging.getLogger(__name__)


class IndexView(TemplateView):
    """View for the finance index page."""

    def get(self, request, *args, **kwargs):
        # Get days for progression calculation
        form = IndexForm(request.GET or None)
        days = 30

        if form.is_valid():
            days = form.cleaned_data["days"]

        context = {
            "form": form,
            "days": days,
            "savings_accounts": [],
            "investment_accounts": [],
        }

        # Get accounts
        saving_accounts: QuerySet[SavingAccount] = SavingAccount.objects.filter(
            is_active=True
        )
        investment_accounts: QuerySet[InvestmentAccount] = (
            InvestmentAccount.objects.filter(is_active=True)
        )

        # Calculate current balance and progression for each account
        for account in saving_accounts:
            context["savings_accounts"].append(
                {"model": account, "progression": account.get_progression(days)}
            )

        for account in investment_accounts:
            context["investment_accounts"].append(
                {
                    "model": account,
                    "progression": account.get_progression(days),
                }
            )

        return render(request, "finance/index.html", context)
