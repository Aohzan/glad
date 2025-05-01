from django.db import models
from djmoney.models.fields import MoneyField

from base.models import BaseModel, Household
from glad import settings


class Property(BaseModel):
    """Model representing a property."""

    PROPERTY_TYPE = [
        ("HO", "House"),
        ("AP", "Apartment"),
        ("CO", "Condo"),
        ("LA", "Land"),
        ("OT", "Other"),
    ]

    id = models.AutoField(primary_key=True)
    property_type = models.CharField(
        max_length=2,
        choices=PROPERTY_TYPE,
        null=False,
        default="OT",
    )
    household = models.ForeignKey(Household, on_delete=models.CASCADE, null=False)
    name = models.CharField(max_length=255, null=False)
    address = models.CharField(max_length=255, null=False)
    is_active = models.BooleanField(default=True)
    value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency=settings.DEFAULT_CURRENCY,
    )

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    class Meta:
        verbose_name_plural = "properties"


# class PropertyValue(BaseModel):
#     """Model representing a property value."""

#     property = models.ForeignKey(Property, on_delete=models.CASCADE, null=False)
#     value = models.DecimalField(max_digits=10, decimal_places=2, null=False)
#     date = models.DateField(null=False)

#     def __str__(self) -> str:
#         """String representation of the PropertyValue model."""
#         return f"{self.property.name} - {self.value} on {self.date}"
