"""Models for finance-related entities such as accounts, account types, and balances."""

import datetime
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from finance.utils import AccountProgression


class SavingAccountType(BaseModel):
    """Model representing an account type."""

    name = models.CharField(max_length=255, null=False)
    code = models.CharField(max_length=10, null=True)

    def __str__(self) -> str:
        """String representation of the AccountType model."""
        if self.code:
            return str(self.code)
        return str(self.name)

    class Meta:
        ordering = ["name"]


class SavingAccount(BaseModel):
    """Saving account has a balance."""

    account_type = models.ForeignKey(
        SavingAccountType, on_delete=models.CASCADE, null=False
    )
    name = models.CharField(max_length=255, null=False)
    owner = models.CharField(max_length=255, null=True, blank=True)
    institution = models.CharField(max_length=255, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    opening_date = models.DateField(default=datetime.date.today, null=False)
    closing_date = models.DateField(null=True, blank=True)

    initial_balance = MoneyField(max_digits=10, decimal_places=2, default=0, null=False)
    initial_balance_date = models.DateField(
        _("Initial balance date"), default=datetime.date.today, null=False
    )

    @property
    def current_balance(self) -> Money:
        """Lazily get the current balance using get_balance()."""
        return self.get_balance()

    @property
    def currency(self) -> str:
        """Get the currency of the initial balance."""
        return self.initial_balance.currency

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text=_("Interest rate in percentage"),
    )

    def get_balance(self, max_date: datetime.datetime | None = None) -> Money:
        """Get the balance of the account at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.now()
        current_balance = (
            SavingAccountBalance.objects.filter(
                account=self, balance_date__lte=max_date
            )
            .order_by("-balance_date")
            .first()
        )
        if current_balance:
            return current_balance.balance
        return self.initial_balance

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the account over a specific number of days."""
        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        return AccountProgression(
            current_balance=self.get_balance(),
            old_balance=self.get_balance(max_date=x_days_ago),
        )


class SavingAccountBalance(BaseModel):
    """Model representing the balance of an account."""

    account = models.ForeignKey(
        SavingAccount, related_name="balances", on_delete=models.CASCADE, null=False
    )
    balance = MoneyField(max_digits=10, decimal_places=2)
    balance_date = models.DateField(default=datetime.date.today, null=False)

    class Meta:
        ordering = ["-balance_date"]


class SavingAccountDeposit(BaseModel):
    """Model representing a deposit in an account."""

    account = models.ForeignKey(
        SavingAccount, related_name="deposits", on_delete=models.CASCADE, null=False
    )
    amount = MoneyField(max_digits=10, decimal_places=2, default=0)
    deposit_date = models.DateField(default=datetime.date.today, null=False)
    source = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-deposit_date"]
