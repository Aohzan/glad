"""Abstract base models shared by investment and saving account models."""

import datetime
from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from moneyed import Money

from base.models import BaseModel
from finance.utils import AccountProgression


class ActiveAccountManager(models.Manager):
    """Default manager that provides an ``active()`` shortcut queryset."""

    def active(self):
        """Return only active accounts (``is_active=True``)."""
        return self.filter(is_active=True)


class AbstractAccountType(BaseModel):
    """Abstract base for account-type lookup models.

    Subclasses must define ``verbose_name`` / ``verbose_name_plural`` in their
    own ``Meta`` and override ``__str__`` as needed.
    """

    class Meta:
        abstract = True
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name", "code"]),
        ]
        unique_together = ("name", "code")

    name = models.CharField(max_length=255, null=False)
    code = models.CharField(max_length=10, null=True, blank=True)


class AbstractAccount(BaseModel):
    """Abstract base for account models (saving, investment …).

    Provides the common set of descriptive fields and helpers so that concrete
    subclasses only need to declare type-specific fields (e.g. ``interest_rate``
    or ``opening_cash_value``) and their own ``get_value()`` / ``currency``.
    """

    objects = ActiveAccountManager()

    class Meta:
        abstract = True
        ordering = ["account_type", "name", "owner", "institution"]
        indexes = [
            models.Index(fields=["account_type", "name", "owner", "institution"]),
        ]
        unique_together = ("account_type", "name", "owner", "institution")

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
    is_active = models.BooleanField(default=True)
    is_favorite = models.BooleanField(
        default=False,
        verbose_name=_("Favorite"),
        help_text=_(
            "Mark this account as a favorite for quick access in the navigation menu."
        ),
    )
    closing_date = models.DateField(null=True, blank=True)

    @property
    def current_value(self):
        """Lazily compute the current value via ``get_value()``."""
        return self.get_value()  # ty: ignore[unresolved-attribute]

    def __str__(self) -> str:
        """String representation shared by all concrete account models."""
        account_name: str = ""
        if self.name and self.name in [self.account_type.name, self.account_type.code]:  # ty: ignore[unresolved-attribute]
            account_name = str(self.name)
        elif self.name:
            account_name = f"{self.account_type} {self.name}"  # ty: ignore[unresolved-attribute]
        else:
            account_name = str(self.account_type)  # ty: ignore[unresolved-attribute]
        return account_name + self._account_name_suffix()

    def _account_name_suffix(self) -> str:
        """Return the owner / institution / closed suffix shared by all account __str__."""
        suffix = ""
        if self.owner:
            suffix += f" {self.owner}"
        if self.institution:
            suffix += f" {_('at')} {self.institution}"
        if not self.is_active:
            suffix += f" {_('(closed)')}"
        return suffix

    @property
    def opening_amount(self) -> "Money":
        """Return the opening value as a Money object.

        Concrete subclasses must override this property to point to their
        specific opening-value field (e.g. ``opening_cash_value`` or
        ``opening_value``).
        """
        raise NotImplementedError  # pragma: no cover

    def compute_capital_gain(self) -> "tuple[Money, Money]":
        """Compute and return ``(total_deposits, capital_gain)`` as Money objects.

        Uses the deposits queryset common to all account types and the
        subclass-provided ``opening_amount`` property.
        """
        from django.db.models import Sum
        from moneyed import Money

        total_deposits_amount = (
            self.deposits.aggregate(total=Sum("amount"))["total"] or 0  # ty: ignore[unresolved-attribute]
        )
        total_deposits = Money(total_deposits_amount, self.currency)  # ty: ignore[unresolved-attribute]
        current_value = self.current_value
        capital_gain = Money(
            current_value.amount - self.opening_amount.amount - total_deposits_amount,
            self.currency,  # ty: ignore[unresolved-attribute]
        )
        return total_deposits, capital_gain

    def get_progression(self, days: int) -> "AccountProgression":
        """Return the value progression over *days* days, net of deposits.

        Concrete subclasses may override this method if their deposit model
        uses a field name other than ``deposit_date``.
        """
        from django.db.models import Sum
        from moneyed import Money

        x_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        current_value = self.get_value()  # ty: ignore[unresolved-attribute]
        old_value = self.get_value(max_date=x_days_ago)  # ty: ignore[unresolved-attribute]

        deposits_sum = self.deposits.filter(  # ty: ignore[unresolved-attribute]
            deposit_date__gte=x_days_ago.date(),
            deposit_date__lte=datetime.date.today(),
        ).aggregate(total=Sum("amount"))["total"]

        deposits_during_period = Money(deposits_sum or 0, current_value.currency)

        return AccountProgression(
            current_value=current_value,
            old_value=old_value,
            deposits=deposits_during_period,
        )
