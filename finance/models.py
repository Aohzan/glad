from datetime import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from djmoney.models.fields import MoneyField

from base.models import BaseModel, Household
from glad import settings


class AccountType(BaseModel):
    """Model representing an account subcategory."""

    class CATEGORY(models.TextChoices):
        CHECKING = "CH", _("Checking")
        SAVINGS = "SA", _("Savings")
        INVESTMENT = "IN", _("Investment")

    name = models.CharField(max_length=255, null=False)
    code = models.CharField(max_length=10, null=True)
    category = models.CharField(
        max_length=2,
        choices=CATEGORY,
        null=False,
    )
    country = CountryField(null=True, blank=True)

    def __str__(self) -> str:
        """String representation of the AccountSubcategory model."""
        display = "[" + self.get_category_display() + \
            "] "  # pylint: disable=no-member
        if self.code:
            return display + str(self.code) + " (" + str(self.name) + ")"
        return display + str(self.name)

    @classmethod
    def get(cls, country: str) -> list["AccountType"]:
        """Get all subcategories for a given country."""
        return cls.objects.filter(country=country)  # pylint: disable=no-member


class Account(BaseModel):
    """Model representing an account."""

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, null=False)
    subcategory = models.ForeignKey(
        AccountType, on_delete=models.CASCADE, null=False)
    name = models.CharField(max_length=255, null=False)
    owner = models.CharField(max_length=255, null=True)
    institution = models.CharField(max_length=255, null=True)
    commentaire = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    initial_balance = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency=settings.DEFAULT_CURRENCY,
    )

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    @classmethod
    def get(cls, household_id: int) -> list["Account"]:
        """Get all accounts for a given household."""
        return cls.objects.filter(household_id=household_id)  # pylint: disable=no-member

    @property
    def current_balance(self) -> MoneyField:
        """Get the current balance of the account."""
        balance = AccountBalance.objects.filter(
            account=self).order_by('-balance_date').first()
        if balance:
            return balance.balance
        return self.initial_balance


class AccountTransaction(BaseModel):
    """Model representing a transaction in an account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=False)
    amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency=settings.DEFAULT_CURRENCY,
    )
    description = models.CharField(max_length=255, null=True)
    transaction_date = models.DateTimeField(default=datetime.now, null=False)

    def __str__(self) -> str:
        """String representation of the AccountTransaction model."""
        return (
            str(self.description)
            + " - "
            + str(self.amount)
            + " - "
            + str(self.transaction_date)
        )


class AccountBalance(BaseModel):
    """Model representing the balance of an account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=False)
    balance = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency=settings.DEFAULT_CURRENCY,
    )
    balance_date = models.DateTimeField(default=datetime.now, null=False)

    def __str__(self) -> str:
        """String representation of the AccountBalance model."""
        return (
            str(self.account)
            + " - "
            + str(self.balance)
            + " - "
            + str(self.balance_date)
        )
