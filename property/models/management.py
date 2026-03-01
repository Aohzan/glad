"""Models for third-party property management: ManagementMandate."""

import builtins

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField

from base.models import BaseModel

_property = (
    builtins.property
)  # alias before any field named "property" shadows the built-in


class ManagementMandate(BaseModel):
    """
    A dated management mandate linking a property to a manager.

    Multiple mandates are allowed per property with non-overlapping dates.
    end_date=None means the mandate is currently active.
    """

    class FeeType(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage of rent")
        FIXED = "fixed", _("Fixed monthly fee")
        MIXED = "mixed", _("Percentage + fixed fee")

    class Meta:
        verbose_name = _("management mandate")
        verbose_name_plural = _("management mandates")
        ordering = ["-start_date"]

    property = models.ForeignKey(
        "property.Property",
        on_delete=models.PROTECT,
        related_name="mandates",
        verbose_name=_("Property"),
    )
    manager_name = models.CharField(
        max_length=200, verbose_name=_("Manager name"), default=""
    )
    manager_address = models.TextField(blank=True, verbose_name=_("Address"))
    manager_phone = models.CharField(max_length=30, blank=True, verbose_name=_("Phone"))
    manager_email = models.EmailField(blank=True, verbose_name=_("Email"))
    start_date = models.DateField(verbose_name=_("Start date"))
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("End date"),
        help_text=_("Leave empty if this mandate is currently active."),
    )
    fee_type = models.CharField(
        max_length=20,
        choices=FeeType.choices,
        default=FeeType.PERCENTAGE,
        verbose_name=_("Fee type"),
    )
    fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fee percentage (%)"),
        help_text=_("Percentage of collected rent, e.g. 7.50 for 7.5%."),
    )
    fixed_fee = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fixed monthly fee"),
    )
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        status = _("active") if self.is_active else str(self.end_date)
        return (
            f"{self.property.name} — {self.manager_name} ({self.start_date} → {status})"
        )

    @_property
    def is_active(self) -> bool:
        """Return True if this mandate has no end date (currently active)."""
        return self.end_date is None
