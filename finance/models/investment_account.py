"""Models for investment accounts, account types, holdings, and deposits."""

import datetime
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from finance.models.base import AbstractAccount, AbstractAccountType
from finance.utils import AccountProgression


class InvestmentAccountType(AbstractAccountType):
    """Model representing an investment account type."""

    class Meta(AbstractAccountType.Meta):
        verbose_name = _("investment account type")
        verbose_name_plural = _("investment account types")

    def __str__(self) -> str:
        """String representation — prefer code, fall back to name."""
        if self.code:
            return str(self.code)
        return str(self.name)


class InvestmentAccount(AbstractAccount):
    """Investment account has a cash value and multiple holdings."""

    deposits: models.Manager["InvestmentAccountDeposit"]
    cash_values: models.Manager["InvestmentAccountCash"]

    class Meta(AbstractAccount.Meta):
        verbose_name = _("investment account")
        verbose_name_plural = _("investment accounts")

    account_type = models.ForeignKey(
        InvestmentAccountType, on_delete=models.CASCADE, null=False
    )
    opening_cash_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),  # type: ignore[call-arg]
        null=False,
    )

    @property
    def currency(self) -> str:
        """Get the currency of the initial value."""
        return str(self.opening_cash_value.currency)

    @property
    def opening_amount(self) -> Money:
        """Return opening_cash_value as the canonical opening amount."""
        return self.opening_cash_value

    @property
    def current_cash_value(self) -> Money:
        """Lazily get the current cash amount."""
        return self.get_cash_value()

    def get_cash_value(
        self, max_date: datetime.datetime | datetime.date | None = None
    ) -> Money:
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
        return Money(
            self.opening_cash_value.amount, str(self.opening_cash_value.currency)
        )

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
            cash_value_amount = Decimal(str(self.opening_cash_value.amount))

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

    def get_cash_progression(self, days: int) -> AccountProgression:
        """Get the cash progression of the account over a specific number of days."""
        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_cash_value = self.get_cash_value()
        old_cash_value = self.get_cash_value(max_date=x_days_ago)

        return AccountProgression(
            current_value=current_cash_value,
            old_value=old_cash_value,
        )

    def subtract_cash(
        self, amount: Money, at_date: datetime.datetime | datetime.date
    ) -> None:
        """Subtract *amount* from the account cash at *at_date* by creating a new cash record."""
        current_cash = self.get_cash_value(max_date=at_date)
        new_value = Money(current_cash.amount - amount.amount, self.currency)
        cash_date = (
            at_date.date() if isinstance(at_date, datetime.datetime) else at_date
        )
        InvestmentAccountCash.objects.create(
            account=self, value_date=cash_date, value=new_value
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
    amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=False,
        help_text=_("Use a negative value to record a withdrawal"),
    )
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
        max_digits=16, decimal_places=6, null=True, blank=True
    )
    initial_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),  # type: ignore[call-arg]
    )
    initial_valuation_date = models.DateField(default=datetime.date.today, null=False)

    @property
    def short_name(self) -> str:
        """Get a short name for the holding."""
        if self.code and not self.name:
            return str(self.code)
        if self.name and not self.code:
            return str(self.name)
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
        return Decimal(str(self.initial_value.amount))

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
        return Decimal(str(self.initial_quantity)) if self.initial_quantity else None

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

    holding_id: int

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
        max_digits=16,
        decimal_places=6,
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
