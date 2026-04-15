"""Models for lease management: Tenant, Lease, LeaseTenant."""

import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel


class Tenant(BaseModel):
    """A tenant who can be associated with one or more leases."""

    class Meta:
        verbose_name = _("tenant")
        verbose_name_plural = _("tenants")
        ordering = ["last_name", "first_name"]

    first_name = models.CharField(max_length=100, verbose_name=_("First name"))
    last_name = models.CharField(max_length=100, verbose_name=_("Last name"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Phone"))
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Lease(BaseModel):
    """A rental lease linking a property to one or more tenants."""

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
    tenants = models.ManyToManyField(
        Tenant,
        through="LeaseTenant",
        related_name="leases",
        blank=True,
    )
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
        default=0,
        default_currency="EUR",
        verbose_name=_("Charges provision"),
    )
    deposit_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency="EUR",
        verbose_name=_("Security deposit"),
    )
    periodicity = models.CharField(
        max_length=20,
        choices=Periodicity.choices,
        default=Periodicity.MONTHLY,
        verbose_name=_("Periodicity"),
    )
    # IRL indexation — prévu dès le modèle, activable en V2
    irl_indexed = models.BooleanField(
        default=False,
        verbose_name=_("IRL indexed"),
        help_text=_("Whether this lease is indexed on the IRL rent index."),
    )
    irl_reference_quarter = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("IRL reference quarter"),
        help_text=_("Reference quarter for IRL indexation, e.g. T1-2024."),
    )
    irl_reference_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("IRL reference value"),
    )
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        tenants_str = ", ".join(str(t) for t in self.tenants.all()[:2])
        return f"{self.property.name} — {tenants_str or _('No tenant')} ({self.start_date})"

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


class LeaseTenant(BaseModel):
    """Through model linking tenants to leases (supports colocation and staggered arrivals)."""

    class Meta:
        verbose_name = _("lease tenant")
        verbose_name_plural = _("lease tenants")
        unique_together = [("lease", "tenant")]

    lease = models.ForeignKey(
        Lease,
        on_delete=models.CASCADE,
        related_name="lease_tenants",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="lease_tenants",
    )
    is_primary = models.BooleanField(
        default=True,
        verbose_name=_("Primary tenant"),
    )
    join_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Join date"),
        help_text=_(
            "Date when this tenant joined the lease (if different from lease start)."
        ),
    )
    leave_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Leave date"),
        help_text=_("Date when this tenant left (colocation partial exit)."),
    )

    def __str__(self) -> str:
        return f"{self.tenant} @ {self.lease}"
