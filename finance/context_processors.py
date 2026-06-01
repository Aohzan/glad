"""Context processors for the finance app."""

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount


def nav_accounts(request):
    """Expose favorite active accounts for the global navigation dropdown."""
    if not request.user.is_authenticated:
        return {"nav_accounts": [], "nav_accounts_any": False}
    saving_favorites = list(
        SavingAccount.objects.filter(is_active=True, is_favorite=True).order_by(
            "account_type", "name"
        )
    )
    investment_favorites = list(
        InvestmentAccount.objects.filter(is_active=True, is_favorite=True).order_by(
            "account_type", "name"
        )
    )
    has_any = (
        SavingAccount.objects.filter(is_active=True).exists()
        or InvestmentAccount.objects.filter(is_active=True).exists()
    )
    return {
        "nav_accounts": saving_favorites + investment_favorites,
        "nav_accounts_saving": saving_favorites,
        "nav_accounts_investment": investment_favorites,
        "nav_accounts_any": has_any,
    }
