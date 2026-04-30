"""Abstract base models shared by investment and saving account models."""

import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel
from finance.utils import AccountProgression


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
    closing_date = models.DateField(null=True, blank=True)

    @property
    def current_value(self):
        """Lazily compute the current value via ``get_value()``."""
        return self.get_value()  # ty: ignore[unresolved-attribute]

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
