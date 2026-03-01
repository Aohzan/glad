"""Models for finance-related entities such as accounts, account types, and values."""

import datetime
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from finance.utils import AccountProgression


class InvestmentAccountType(BaseModel):
    """Model representing an account type."""

    class Meta:
        verbose_name = _("investment account type")
        verbose_name_plural = _("investment account types")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name", "code"]),
        ]
        unique_together = ("name", "code")

    name = models.CharField(max_length=255, null=False)
    code = models.CharField(max_length=10, null=True, blank=True)

    def __str__(self) -> str:
        """String representation of the AccountType model."""
        if self.code:
            return self.code
        return self.name


class InvestmentAccount(BaseModel):
    """Investment account has a cash value and multiple holdings."""

    class Meta:
        verbose_name = _("investment account")
        verbose_name_plural = _("investment accounts")
        ordering = ["account_type", "name", "owner", "institution"]
        indexes = [
            models.Index(fields=["account_type", "name", "owner", "institution"]),
        ]
        unique_together = ("account_type", "name", "owner", "institution")

    account_type = models.ForeignKey(
        InvestmentAccountType, on_delete=models.CASCADE, null=False
    )
    name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Name of the account (optional)"),
    )
    owner = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Owner of the account (optional)"),
    )
    institution = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Institution where the account is held (optional)"),
    )
    commentaire = models.TextField(null=True, blank=True)

    opening_date = models.DateField(default=datetime.date.today, null=False)
    opening_cash_value = MoneyField(
        max_digits=10, decimal_places=2, default=0, null=False
    )

    is_active = models.BooleanField(default=True)
    closing_date = models.DateField(null=True, blank=True)

    @property
    def current_value(self) -> Money:
        """Lazily get the current value using get_value()."""
        return self.get_value()

    @property
    def currency(self) -> str:
        """Get the currency of the initial value."""
        return self.opening_cash_value.currency

    @property
    def current_cash_value(self) -> Money:
        """Lazily get the current cash amount."""
        return self.get_cash_value()

    def __str__(self) -> str:
        """String representation of the Account model."""
        account_name: str = ""
        if self.name and self.name in [self.account_type.name, self.account_type.code]:
            account_name = self.name
        elif self.name:
            account_name = f"{str(self.account_type)} {self.name}"
        else:
            account_name = str(self.account_type)
        if self.owner:
            account_name += f" {self.owner}"
        if self.institution:
            account_name += f" {_('at')} {self.institution}"
        if not self.is_active:
            account_name += f" {_('(closed)')}"
        return account_name

    def get_cash_value(self, max_date: datetime.datetime | None = None) -> Money:
        """Get the value of the account at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.now()
        current_cash_value = (
            InvestmentAccountCash.objects.filter(account=self, value_date__lte=max_date)
            .order_by("-value_date")
            .first()
        )
        if current_cash_value:
            return current_cash_value.value
        return self.opening_cash_value

    def get_value(
        self, max_date: datetime.datetime | datetime.date | None = None
    ) -> Money:
        """Get the value of the account at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.today()

        # Convert datetime to date for comparison with DateField
        if isinstance(max_date, datetime.datetime):
            date_for_query = max_date.date()
        else:
            date_for_query = max_date

        # Get the most recent cash value before max_date
        cash_value_amount: Decimal = Decimal("0")
        if (
            current_value := InvestmentAccountCash.objects.filter(
                account=self, value_date__lte=date_for_query
            )
            .order_by("-value_date")
            .first()
        ):
            cash_value_amount = current_value.value.amount
        else:
            # If no cash value found, use the initial cash value
            cash_value_amount = self.opening_cash_value.amount

        holdings_value_total: Decimal = Decimal("0")
        holdings = InvestmentAccountHolding.objects.filter(
            account=self, is_active=True
        ).order_by("name")
        if not holdings.exists():
            return Money(cash_value_amount, self.currency)

        for holding in holdings:
            holding_value = (
                InvestmentAccountHoldingHistory.objects.filter(
                    holding=holding, valuation_date__lte=max_date
                )
                .order_by("-valuation_date")
                .first()
            )
            if holding_value:
                holdings_value_total += holding_value.value.amount
            else:
                holdings_value_total += holding.initial_value.amount
        return Money(cash_value_amount + holdings_value_total, self.currency)

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the account over a specific number of days."""
        from django.db.models import Sum

        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_value = self.get_value()
        old_value = self.get_value(max_date=x_days_ago)

        # Calculate deposits during the period
        deposits_sum = self.deposits.filter(
            deposit_date__gte=x_days_ago.date(),
            deposit_date__lte=datetime.datetime.today(),
        ).aggregate(total=Sum("amount"))["total"]

        # Convert Decimal to Money object
        deposits_during_period = Money(deposits_sum or 0, current_value.currency)

        return AccountProgression(
            current_value=current_value,
            old_value=old_value,
            deposits=deposits_during_period,
        )

    def get_cash_progression(self, days: int) -> AccountProgression:
        """Get the cash progression of the account over a specific number of days."""
        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_cash_value = self.get_cash_value()
        old_cash_value = self.get_cash_value(max_date=x_days_ago)

        return AccountProgression(
            current_value=current_cash_value,
            old_value=old_cash_value,
        )


class InvestmentAccountCash(BaseModel):
    """Model representing the cash value of an account."""

    class Meta:
        verbose_name = _("cash value of investment account")
        verbose_name_plural = _("cash values of investment accounts")
        ordering = ["account", "-value_date"]
        indexes = [
            models.Index(fields=["account", "value_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "value_date", "value"],
                name="unique_investment_account_cash",
            ),
        ]

    account = models.ForeignKey(
        InvestmentAccount,
        related_name="cash_values",
        on_delete=models.CASCADE,
        null=False,
    )
    value = MoneyField(max_digits=10, decimal_places=2)
    value_date = models.DateField(default=datetime.date.today, null=False)


class InvestmentAccountDeposit(BaseModel):
    """Model representing a deposit in an account."""

    class Meta:
        verbose_name = _("deposit on investment account")
        verbose_name_plural = _("deposits on investment accounts")
        ordering = ["account", "-deposit_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "deposit_date", "amount_currency", "amount"],
                name="unique_investment_account_deposit",
            ),
        ]

    account = models.ForeignKey(
        InvestmentAccount, related_name="deposits", on_delete=models.CASCADE, null=False
    )
    amount = MoneyField(max_digits=10, decimal_places=2, null=False)
    deposit_date = models.DateField(default=datetime.date.today, null=False)
    source = models.TextField(null=True, blank=True)
    update_account_cash = models.BooleanField(
        default=True,
        help_text=_("Add this deposit amount to the account cash value"),
    )


class InvestmentAccountHolding(BaseModel):
    """Model representing the holding of an account."""

    class Meta:
        verbose_name = _("holding of investment account")
        verbose_name_plural = _("holdings of investment accounts")
        ordering = ["account", "name", "code"]
        indexes = [
            models.Index(fields=["account", "name", "code"]),
        ]

    account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, null=False)
    name = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=10, null=True, blank=True)
    isin = models.CharField(max_length=12, null=True, blank=True)
    fees = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(0),
        help_text=_("Fees associated with the holding, in percentage"),
    )
    issuer = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Issuer of the holding"),
    )
    is_active = models.BooleanField(default=True)
    initial_quantity = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    initial_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    initial_valuation_date = models.DateField(default=datetime.date.today, null=False)

    @property
    def short_name(self) -> str:
        """Get a short name for the holding."""
        if self.code and not self.name:
            return self.code
        if self.name and not self.code:
            return self.name
        return f"{self.name} ({self.code})"

    def __str__(self) -> str:
        """String representation of the InvestmentAccountHolding model."""
        holding_name = _("{} in {}.").format(self.short_name, str(self.account))
        if not self.is_active:
            holding_name += f" {_('(closed)')}"
        return holding_name

    @property
    def value(self) -> Money:
        """Get the current value of the holding."""
        return Money(self.get_value(), self.account.currency)

    @property
    def quantity(self) -> Decimal | None:
        """Return the currently quantity of this holding."""
        return self.get_quantity()

    def get_value(
        self, max_date: datetime.datetime | datetime.date | None = None
    ) -> Decimal:
        """Get the value of the holding at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.today()

        # For DateTimeField, we can use the datetime directly
        holding_value = (
            InvestmentAccountHoldingHistory.objects.filter(
                holding=self, valuation_date__lte=max_date
            )
            .order_by("-valuation_date")
            .first()
        )
        if holding_value:
            return holding_value.value.amount
        return self.initial_value.amount

    def get_quantity(
        self, max_date: datetime.datetime | datetime.date | None = None
    ) -> Decimal | None:
        """Get the quantity of the holding at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.now()

        holding_last_value = (
            InvestmentAccountHoldingHistory.objects.filter(
                holding=self, valuation_date__lte=max_date
            )
            .order_by("-valuation_date")
            .first()
        )
        if holding_last_value:
            return holding_last_value.quantity
        return self.initial_quantity

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the holding over a specific number of days."""
        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_value_decimal = self.get_value()
        old_value_decimal = self.get_value(max_date=x_days_ago)

        # Convert Decimal to Money objects
        current_value = Money(current_value_decimal, self.account.currency)
        old_value = Money(old_value_decimal, self.account.currency)

        return AccountProgression(
            current_value=current_value,
            old_value=old_value,
        )


class InvestmentAccountHoldingHistory(BaseModel):
    """Model representing the value of an account holding."""

    class Meta:
        verbose_name = _("history of holding")
        verbose_name_plural = _("history of holdings")
        ordering = [
            "-valuation_date",
            "holding",
        ]
        indexes = [
            models.Index(fields=["holding", "valuation_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "holding",
                    "valuation_date",
                    "value",
                    "quantity",
                ],
                name="unique_investment_holding_history",
            ),
        ]

    holding = models.ForeignKey(
        InvestmentAccountHolding, on_delete=models.CASCADE, null=False
    )
    value = MoneyField(
        help_text=_("Value of the holding share at the moment of valuation"),
        max_digits=10,
        decimal_places=2,
        null=False,
    )
    valuation_date = models.DateTimeField(default=datetime.datetime.now, null=False)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("Quantity of the holding at the moment of valuation"),
    )
    cash_used = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Amount of cash used for this transaction (will be subtracted from account cash)"
        ),
    )

    def __str__(self) -> str:
        """String representation of the InvestmentAccountHoldingValue model."""
        return f"{self.holding} - {self.value} on {self.valuation_date.strftime('%Y-%m-%d') if hasattr(self.valuation_date, 'strftime') else self.valuation_date}"

    def total_value(self) -> Decimal:
        """Get the total value of the holding."""
        return self.value.amount * self.quantity
