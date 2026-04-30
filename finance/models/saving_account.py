"""Models for finance-related entities such as accounts, account types, and values."""

import datetime
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from finance.models.base import AbstractAccount, AbstractAccountType


class SavingAccountType(AbstractAccountType):
    """Model representing a saving account type."""

    class Meta(AbstractAccountType.Meta):
        verbose_name = _("saving account type")
        verbose_name_plural = _("saving account types")

    def __str__(self) -> str:
        """String representation — show name with code in parentheses if set."""
        if self.code:
            return f"{self.name} ({self.code})"
        return str(self.name)


class SavingAccount(AbstractAccount):
    """Saving account has a value."""

    deposits: models.Manager["SavingAccountDeposit"]

    class Meta(AbstractAccount.Meta):
        verbose_name = _("saving account")
        verbose_name_plural = _("saving accounts")

    account_type = models.ForeignKey(
        SavingAccountType, on_delete=models.CASCADE, null=False
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text=_("Interest rate in percentage"),
    )
    opening_value = MoneyField(max_digits=10, decimal_places=2, default=0, null=False)

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
        return account_name + self._account_name_suffix()

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
