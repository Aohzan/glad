"""Base views for the Django application."""

from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount
from property.models import Property


class IndexView(TemplateView):
    """View for the index page."""

    template_name = "index.html"

    @method_decorator(login_not_required)
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, self.template_name, {})

        investment_accounts = InvestmentAccount.objects.filter(is_active=True)
        saving_accounts = SavingAccount.objects.filter(is_active=True)
        properties = Property.objects.filter(is_active=True)

        total_saving_accounts_today = sum(
            account.get_balance() for account in saving_accounts
        )
        total_investment_accounts_today = sum(
            account.get_value() for account in investment_accounts
        )
        total_properties_value = sum(property.get_value() for property in properties)

        context = {
            "total_saving_accounts_balance": total_saving_accounts_today,
            "total_investment_accounts_balance": total_investment_accounts_today,
            "total_properties_value": total_properties_value,
            "net_worth": (
                total_saving_accounts_today
                + total_investment_accounts_today
                + total_properties_value
            ),
        }
        return render(request, self.template_name, context)
