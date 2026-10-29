"""Models for lease management: Lease and its parties."""

import builtins
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from base.models import BaseModel

_property = builtins.property


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
        MOBILITY = "mobility", _("Mobility (furnished)")
        STUDENT = "student", _("Student (furnished)")
        COMMERCIAL = "commercial", _("Commercial")
        OTHER = "other", _("Other")

    class Periodicity(models.TextChoices):
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")

    class ChargesMode(models.TextChoices):
        PROVISION = "provision", _("Provision, reconciled every year")
        FLAT = "flat", _("Flat rate")

    #: Lease types of a furnished dwelling.
    FURNISHED_TYPES = (LeaseType.FURNISHED, LeaseType.MOBILITY, LeaseType.STUDENT)

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
    notice_by = models.CharField(
        max_length=10,
        choices=[("tenant", _("The tenant")), ("landlord", _("The landlord"))],
        blank=True,
        verbose_name=_("Notice given by"),
    )
    signed_date = models.DateField(
        null=True, blank=True, verbose_name=_("Signature date")
    )
    duration_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name=_("Duration (months)"),
        help_text=_(
            "Leave empty for the legal duration: 3 years empty, 1 year furnished, "
            "9 months for a student."
        ),
    )
    payment_day = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
        verbose_name=_("Payment day"),
        help_text=_("Day of the month the rent is due."),
    )
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
    charges_mode = models.CharField(
        max_length=20,
        choices=ChargesMode.choices,
        default=ChargesMode.PROVISION,
        verbose_name=_("Charges"),
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
    irl_reference_quarter = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=[(1, _("Q1")), (2, _("Q2")), (3, _("Q3")), (4, _("Q4"))],
        verbose_name=_("IRL reference quarter"),
        help_text=_(
            "Quarter of the rent reference index named in the lease, usually the "
            "last one published when it was signed."
        ),
    )
    irl_reference_value = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("IRL reference value"),
        help_text=_("IRL value of the current rent (at signing or last revision)."),
    )
    last_rent_revision_date = models.DateField(
        null=True, blank=True, verbose_name=_("Last rent revision")
    )
    send_rent_calls = models.BooleanField(
        default=False,
        verbose_name=_("Send the rent calls"),
        help_text=_(
            "Email the rent notice to the tenants a week before each due date."
        ),
    )
    send_receipts = models.BooleanField(
        default=False,
        verbose_name=_("Send the receipts"),
        help_text=_(
            "Email the receipt to the tenants the day after the rent is checked "
            "as received."
        ),
    )
    notes = models.TextField(blank=True)

    @_property
    def tenants(self) -> list[LeaseParty]:
        """Tenants of the lease, from the prefetched parties when available."""
        if self.pk is None:
            return []
        parties = self.parties.all()  # ty: ignore[unresolved-attribute]
        return [p for p in parties if p.role == LeaseParty.Role.TENANT]

    @_property
    def guarantors(self) -> list[LeaseParty]:
        """Guarantors of the lease, from the prefetched parties when available."""
        if self.pk is None:
            return []
        parties = self.parties.all()  # ty: ignore[unresolved-attribute]
        return [p for p in parties if p.role == LeaseParty.Role.GUARANTOR]

    @_property
    def name(self) -> str:
        """Names of the tenants."""
        return ", ".join(tenant.name for tenant in self.tenants)

    @_property
    def is_furnished(self) -> bool:
        return self.lease_type in self.FURNISHED_TYPES

    def __str__(self) -> str:
        return f"{self.name or _('Lease')} ({self.start_date})"

    def mandate_on(self, date: datetime.date | None = None):
        """Management mandate of the property covering *date* (today), or None."""
        return self.property.mandate_on(date or datetime.date.today())

    @_property
    def is_self_managed(self) -> bool:
        """True when no management mandate covers the lease today."""
        return self.mandate_on() is None

    def is_active_at(self, date: datetime.date) -> bool:
        """Return True if this lease is active on the given date."""
        if self.start_date > date:
            return False
        return not (self.end_date and self.end_date < date)

    def total_rent(self) -> Money:
        """Return rent + charges as a single Money amount."""
        return self.rent_amount + self.charges_amount


class LeaseParty(BaseModel):
    """A tenant or a guarantor of a lease."""

    class Role(models.TextChoices):
        TENANT = "tenant", _("Tenant")
        GUARANTOR = "guarantor", _("Guarantor")

    class GuaranteeType(models.TextChoices):
        JOINT = "joint", _("Joint and several guarantee")
        VISALE = "visale", _("Visale")
        OTHER = "other", _("Other guarantee")

    class Meta:
        verbose_name = _("lease party")
        verbose_name_plural = _("lease parties")
        # "tenant" sorts after "guarantor": tenants come first.
        ordering = ["-role", "pk"]

    lease = models.ForeignKey(
        Lease, on_delete=models.CASCADE, related_name="parties", verbose_name=_("Lease")
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TENANT,
        verbose_name=_("Role"),
    )
    first_name = models.CharField(
        max_length=100, blank=True, verbose_name=_("First name")
    )
    last_name = models.CharField(max_length=100, verbose_name=_("Last name"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Phone"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Birth date"))
    birth_place = models.CharField(
        max_length=100, blank=True, verbose_name=_("Birth place")
    )
    address = models.TextField(
        blank=True,
        verbose_name=_("Address"),
        help_text=_("Postal address, when it is not the rented dwelling."),
    )
    guarantee_type = models.CharField(
        max_length=20,
        choices=GuaranteeType.choices,
        blank=True,
        verbose_name=_("Guarantee"),
    )

    def __str__(self) -> str:
        return self.name

    @_property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
