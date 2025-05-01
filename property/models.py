"""Models for the Property app."""

import datetime
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel


class Property(BaseModel):
    """Model representing a property."""

    HOUSE = "HO"
    APARTMENT = "AP"
    CONDO = "CO"
    LAND = "LA"
    OTHER = "OT"
    PROPERTY_CHOICES = [
        (HOUSE, _("House")),
        (APARTMENT, _("Apartment")),
        (CONDO, _("Condo")),
        (LAND, _("Land")),
        (OTHER, _("Other")),
    ]

    property_type = models.CharField(
        max_length=2,
        choices=PROPERTY_CHOICES,
        null=False,
        default=HOUSE,
        verbose_name=_("Property Type"),
    )
    name = models.CharField(max_length=255, null=False)
    address = models.CharField(max_length=255, null=False)
    is_active = models.BooleanField(default=True)
    initial_value = MoneyField(
        max_digits=10,
        decimal_places=0,
    )
    buying_date = models.DateField(
        null=False,
        verbose_name=_("Buying Date"),
    )
    selling_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Selling Date"),
    )

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    class Meta:
        """Meta options for the Property model."""

        verbose_name_plural = "properties"

    def get_value(self, max_date: datetime.datetime | None = None) -> Money:
        """Get the value of the property at a specific date."""
        if max_date is None:
            max_date = datetime.datetime.now()

        property_values = (
            PropertyValue.objects.filter(property=self, valuation_date__lte=max_date)
            .order_by("-valuation_date")
            .first()
        )

        if property_values:
            return property_values.value

        return self.initial_value


class PropertyValue(BaseModel):
    """Model representing a property value."""

    value = MoneyField(max_digits=10, decimal_places=0, null=False)
    valuation_date = models.DateField(null=False)
    property = models.ForeignKey(
        Property,
        related_name="property_values",
        on_delete=models.CASCADE,
        null=False,
    )

    class Meta:
        ordering = ["-valuation_date"]
