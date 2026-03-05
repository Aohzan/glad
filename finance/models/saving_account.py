"""Models for finance-related entities such as accounts, account types, and values."""

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

    class Meta:
        """Meta options for the AccountType model."""

        verbose_name = _("saving account type")
        verbose_name_plural = _("saving account types")
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
            return f"{self.name} ({self.code})"
        return str(self.name)


class SavingAccount(BaseModel):
    """Saving account has a value."""

    deposits: models.Manager["SavingAccountDeposit"]

    class Meta:
        """Meta options for the SavingAccount model."""

        verbose_name = _("saving account")
        verbose_name_plural = _("saving accounts")
        ordering = ["account_type", "name", "owner", "institution"]
        indexes = [
            models.Index(fields=["account_type", "name", "owner", "institution"]),
        ]
        unique_together = ("account_type", "name", "owner", "institution")

    account_type = models.ForeignKey(
        SavingAccountType, on_delete=models.CASCADE, null=False
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
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text=_("Interest rate in percentage"),
    )

    opening_date = models.DateField(default=datetime.date.today, null=False)
    opening_value = MoneyField(max_digits=10, decimal_places=2, default=0, null=False)
    is_active = models.BooleanField(default=True)
    closing_date = models.DateField(null=True, blank=True)

    @property
    def current_value(self) -> Money:
        """Lazily get the current value using get_value()."""
        return self.get_value()

    @property
    def currency(self) -> str:
        """Get the currency of the initial value."""
        return str(self.opening_value.currency)

    def __str__(self) -> str:
        """String representation of the Account model."""
        account_name: str = ""
        if self.name and self.name in [self.account_type.name, self.account_type.code]:
            account_name = str(self.name)
        elif self.name:
            account_name = f"{self.account_type.name} {self.name}"
        else:
            account_name = str(self.account_type.name) if self.account_type.name else ""
        if self.owner:
            account_name += f" {self.owner}"
        if self.institution:
            account_name += f" {_('at')} {self.institution}"
        if not self.is_active:
            account_name += f" {_('(closed)')}"
        return account_name

    def get_value(
        self, max_date: datetime.datetime | datetime.date | None = None
    ) -> Money:
        """Get the value of the account at a specific date."""

        if max_date is None:
            max_date = datetime.datetime.now()

        # Convert date to datetime for comparison with DateTimeField
        if isinstance(max_date, datetime.date) and not isinstance(
            max_date, datetime.datetime
        ):
            date_for_query = datetime.datetime.combine(
                max_date, datetime.time.max
            )  # Use end of day
        else:
            date_for_query = max_date

        last_value = (
            SavingAccountValue.objects.filter(
                account=self, value_date__lte=date_for_query
            )
            .order_by("-value_date")
            .first()
        )
        if last_value:
            return last_value.value
        return Money(self.opening_value.amount, str(self.opening_value.currency))

    def get_progression(self, days: int) -> AccountProgression:
        """Get the progression of the account over a specific number of days."""
        from django.db.models import Sum

        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_value = self.get_value()
        old_value = self.get_value(max_date=x_days_ago)

        # Calculate deposits during the period
        deposits_sum = self.deposits.filter(
            deposit_date__gte=x_days_ago,
            deposit_date__lte=datetime.datetime.now(),
        ).aggregate(total=Sum("amount"))["total"]

        # Convert Decimal to Money object
        deposits_during_period = Money(deposits_sum or 0, current_value.currency)

        return AccountProgression(
            current_value=current_value,
            old_value=old_value,
            deposits=deposits_during_period,
        )


class SavingAccountValue(BaseModel):
    """Model representing the value of an account."""

    class Meta:
        verbose_name = _("saving account value")
        verbose_name_plural = _("History of saving accounts")
        ordering = ["account", "-value_date"]
        indexes = [
            models.Index(fields=["account", "value_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "value_date", "value"],
                name="unique_saving_account_value",
            ),
        ]

    account = models.ForeignKey(
        SavingAccount, related_name="values", on_delete=models.CASCADE, null=False
    )
    value = MoneyField(max_digits=10, decimal_places=2)
    value_date = models.DateTimeField(default=datetime.datetime.now, null=False)

    def __str__(self) -> str:
        """String representation of the AccountValue model."""
        return f"{self.account} - {self.value} {_('on')} {self.value_date}"


class SavingAccountDeposit(BaseModel):
    """Model representing a deposit in an account."""

    class Meta:
        verbose_name = _("deposit on saving account")
        verbose_name_plural = _("deposits on saving accounts")
        ordering = ["account", "-deposit_date"]
        indexes = [
            models.Index(fields=["account", "deposit_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "deposit_date", "amount_currency", "amount"],
                name="unique_saving_account_deposit",
            ),
        ]

    account = models.ForeignKey(
        SavingAccount, related_name="deposits", on_delete=models.CASCADE, null=False
    )
    amount = MoneyField(max_digits=10, decimal_places=2, default=0)
    deposit_date = models.DateTimeField(default=datetime.datetime.now, null=False)
    source = models.TextField(null=True, blank=True)
    update_account_value = models.BooleanField(
        default=True,
        help_text=_("Add this deposit amount to the account value"),
    )
