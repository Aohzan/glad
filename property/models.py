"""Models for the Property app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField

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
    value = MoneyField(
        max_digits=10,
        decimal_places=0,
    )

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    class Meta:
        """Meta options for the Property model."""

        verbose_name_plural = "properties"


class PropertyValue(BaseModel):
    """Model representing a property value."""

    property = models.ManyToManyField(Property)
    value = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    valuation_date = models.DateField(null=False)

    def __str__(self) -> str:
        """String representation of the PropertyValue model."""
        return f"{self.property.name} - {self.value} on {self.valuation_date}"
