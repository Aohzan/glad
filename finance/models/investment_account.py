"""Models for finance-related entities such as accounts, account types, and balances."""

import datetime
from django.utils import timezone
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from finance.utils import AccountProgression


class InvestmentAccountType(BaseModel):
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


class InvestmentAccount(BaseModel):
    """Investment account has a cash balance and multiple holdings."""

    account_type = models.ForeignKey(
        InvestmentAccountType, on_delete=models.CASCADE, null=False
    )
    name = models.CharField(max_length=255, null=False)
    owner = models.CharField(max_length=255, null=True, blank=True)
    institution = models.CharField(max_length=255, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    opening_date = models.DateField(default=datetime.date.today, null=False)
    closing_date = models.DateField(null=True, blank=True)

    initial_cash_balance = MoneyField(
        max_digits=10, decimal_places=2, default=0, null=False
    )
    initial_cash_balance_date = models.DateField(
        _("Initial cash date"), default=datetime.date.today, null=False
    )

    @property
    def current_value(self) -> Money:
        """Lazily get the current balance using get_balance()."""
        return self.get_value()

    @property
    def currency(self) -> str:
        """Get the currency of the initial balance."""
        return self.initial_cash_balance.currency

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    def get_value(self, max_date: datetime.datetime | None = None) -> Money:
        """Get the balance of the account at a specific date."""
        if max_date is None:
            max_date = timezone.now()

        # Get the most recent cash balance before max_date
        cash_balance: Decimal = Decimal("0")
        if (
            current_balance := InvestmentAccountCash.objects.filter(
                account=self, balance_date__lte=max_date
            )
            .order_by("-balance_date")
            .first()
        ):
            cash_balance = current_balance.balance.amount
        else:
            # If no cash balance found, use the initial cash balance
            cash_balance = self.initial_cash_balance.amount

        holdings_value_total: Decimal = Decimal("0")
        holdings = InvestmentAccountHolding.objects.filter(
            account=self, is_active=True
        ).order_by("name")
        if not holdings.exists():
            return Money(cash_balance, self.currency)

        for holding in holdings:
            holding_balance = (
                InvestmentAccountHoldingHistory.objects.filter(
                    holding=holding, valuation_date__lte=max_date
                )
                .order_by("-valuation_date")
                .first()
            )
            if holding_balance:
                holdings_value_total += holding_balance.value.amount
            else:
                holdings_value_total += holding.initial_value.amount
        return Money(cash_balance + holdings_value_total, self.currency)

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the account over a specific number of days."""
        x_days_ago = timezone.now() - datetime.timedelta(days=days)
        current_balance = self.get_value()
        old_balance = self.get_value(max_date=x_days_ago)
        return AccountProgression(
            current_balance=current_balance,
            old_balance=old_balance,
        )


class InvestmentAccountCash(BaseModel):
    """Model representing the balance of an account."""

    account = models.ForeignKey(
        InvestmentAccount,
        related_name="cash_balances",
        on_delete=models.CASCADE,
        null=False,
    )
    balance = MoneyField(max_digits=10, decimal_places=2)
    balance_date = models.DateField(default=datetime.date.today, null=False)


class InvestmentAccountDeposit(BaseModel):
    """Model representing a deposit in an account."""

    account = models.ForeignKey(
        InvestmentAccount, related_name="deposits", on_delete=models.CASCADE, null=False
    )
    amount = MoneyField(max_digits=10, decimal_places=2, default=0)
    deposit_date = models.DateField(default=datetime.date.today, null=False)
    source = models.TextField(null=True, blank=True)


class InvestmentAccountHolding(BaseModel):
    """Model representing the holding of an account."""

    account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, null=False)
    name = models.CharField(max_length=255, null=True)
    code = models.CharField(max_length=10, null=True)
    is_active = models.BooleanField(default=True)
    initial_quantity = models.PositiveIntegerField(default=0, null=False, blank=False)
    initial_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    initial_valuation_date = models.DateField(default=datetime.date.today, null=False)

    def __str__(self) -> str:
        """String representation of the InvestmentAccountHolding model."""
        return f"[{self.account.name}] {self.name} {self.code}"

    @property
    def value(self) -> Money:
        """Get the current value of the holding."""
        return Money(self.get_value(), self.account.currency)

    def get_value(self, max_date: datetime.datetime | None = None) -> Decimal:
        """Get the value of the holding at a specific date."""
        if max_date is None:
            max_date = timezone.now()
        holding_balance = (
            InvestmentAccountHoldingHistory.objects.filter(
                holding=self, valuation_date__lte=max_date
            )
            .order_by("-valuation_date")
            .first()
        )
        if holding_balance:
            return holding_balance.value.amount
        return self.initial_value.amount

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the holding over a specific number of days."""
        x_days_ago = timezone.now() - datetime.timedelta(days=days)
        current_value_decimal = self.get_value()
        old_value_decimal = self.get_value(max_date=x_days_ago)

        # Convert Decimal to Money objects
        current_value = Money(current_value_decimal, self.account.currency)
        old_value = Money(old_value_decimal, self.account.currency)

        return AccountProgression(
            current_balance=current_value,
            old_balance=old_value,
        )


class InvestmentAccountHoldingHistory(BaseModel):
    """Model representing the balance of an account holding."""

    holding = models.ForeignKey(
        InvestmentAccountHolding, on_delete=models.CASCADE, null=False
    )
    value = MoneyField(
        help_text=_("Value of the holding share at the moment of valuation"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    valuation_date = models.DateTimeField(default=timezone.now, null=False)
    quantity = models.PositiveIntegerField(default=0, null=False, blank=False)

    class Meta:
        verbose_name_plural = "Investment account holding histories"

    def __str__(self) -> str:
        """String representation of the InvestmentAccountHoldingBalance model."""
        return f"{self.holding} - {self.value} on {self.valuation_date.strftime('%Y-%m-%d') if hasattr(self.valuation_date, 'strftime') else self.valuation_date}"

    def total_value(self) -> Decimal:
        """Get the total value of the holding."""
        return self.value.amount * self.quantity
