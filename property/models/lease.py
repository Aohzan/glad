"""Models for lease management: Lease."""

import builtins
import datetime

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from djmoney.models.fields import MoneyField
from djmoney.money import Money

from base.models import BaseModel


class Lease(BaseModel):
    """A rental lease linking a property."""

    class Status(models.TextChoices):
        UPCOMING = "upcoming", _("Upcoming")
        ACTIVE = "active", _("Active")
        NOTICE_PERIOD = "notice", _("Notice period")
        ENDED = "ended", _("Ended")

    class LeaseType(models.TextChoices):
        FURNISHED = "furnished", _("Furnished")
        EMPTY = "empty", _("Empty")
        COMMERCIAL = "commercial", _("Commercial")
        OTHER = "other", _("Other")

    class Periodicity(models.TextChoices):
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")

    class Meta:
        verbose_name = _("lease")
        verbose_name_plural = _("leases")
        ordering = ["-start_date"]

    property = models.ForeignKey(
        "property.Property",
        on_delete=models.PROTECT,
        related_name="leases",
        verbose_name=_("Property"),
    )
    first_name = models.CharField(
        max_length=100, blank=True, verbose_name=_("First name")
    )
    last_name = models.CharField(max_length=100, verbose_name=_("Last name"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Phone"))
    lease_type = models.CharField(
        max_length=20,
        choices=LeaseType.choices,
        default=LeaseType.FURNISHED,
        verbose_name=_("Lease type"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPCOMING,
        verbose_name=_("Status"),
    )
    start_date = models.DateField(verbose_name=_("Start date"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("End date"))
    notice_date = models.DateField(null=True, blank=True, verbose_name=_("Notice date"))
    rent_amount = MoneyField(
        max_digits=10, decimal_places=2, verbose_name=_("Rent (excl. charges)")
    )
    charges_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        default_currency=settings.DEFAULT_CURRENCY,
        verbose_name=_("Charges provision"),
    )
    deposit_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        default_currency=settings.DEFAULT_CURRENCY,
        verbose_name=_("Security deposit"),
    )
    periodicity = models.CharField(
        max_length=20,
        choices=Periodicity.choices,
        default=Periodicity.MONTHLY,
        verbose_name=_("Periodicity"),
    )
    notes = models.TextField(blank=True)

    @builtins.property
    def name(self) -> str:
        """Return the full name of the tenant."""
        return f"{self.first_name or ''} {self.last_name}".strip()

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date})".strip()

    def is_active_at(self, date: datetime.date) -> bool:
        """Return True if this lease is active on the given date."""
        if self.start_date > date:
            return False
        if self.end_date and self.end_date < date:
            return False
        return True

    def total_rent(self) -> Money:
        """Return rent + charges as a single Money amount."""
        return self.rent_amount + self.charges_amount
