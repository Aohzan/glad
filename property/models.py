"""Models for the Property app."""

import datetime
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from property.utils import PropertyProgression, generate_recurring_occurrences


class PropertyLoan(BaseModel):
    """Model representing a property loan."""

    class Meta:
        """Meta options for the PropertyLoan model."""

        verbose_name = _("property loan")
        verbose_name_plural = _("property loans")
        ordering = ["-start_date"]

    property = models.ForeignKey(
        "Property",
        related_name="loans",
        on_delete=models.CASCADE,
        null=False,
    )
    name = models.CharField(
        max_length=255, null=True, blank=True, help_text=_("Optional name for the loan")
    )
    lender = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Lender")
    )
    start_date = models.DateField(null=False, verbose_name=_("Start Date"))
    end_date = models.DateField(null=False, verbose_name=_("End Date"))
    original_amount = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=False,
        verbose_name=_("Original Amount"),
    )
    monthly_payment = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=False,
        verbose_name=_("Monthly Payment"),
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Interest Rate (%)"),
    )
    insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Insurance Rate (%)"),
    )
    insurance = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Insurance"),
    )

    def __str__(self) -> str:
        """String representation of the PropertyLoan model."""
        if self.name:
            return f"{self.property.name} - {self.name}"
        return f"{self.property.name} - {self.original_amount}"

    def taeg_rate(self) -> Decimal:
        """Calculate the TAEG (Taux Annuel Effectif Global) of the loan."""
        if self.start_date is None or self.end_date is None:
            return Decimal("0.0")

        # Simplified TAEG calculation (actual calculation may vary)
        total_interest = (
            self.monthly_payment.amount
            * 12
            * (self.end_date.year - self.start_date.year)
        )
        taeg = (
            (total_interest / self.original_amount.amount)
            * 100
            / (self.end_date.year - self.start_date.year)
        )
        return Decimal(str(taeg))

    def remaining_balance(self, as_of_date: datetime.date | None = None) -> Money:
        """Calculate the remaining balance on the loan as of a specific date."""
        if as_of_date is None:
            as_of_date = datetime.date.today()

        # Cases where the loan is not active
        if (
            self.start_date is None
            or as_of_date < self.start_date
            or self.end_date is None
        ):
            return Money(
                self.original_amount.amount, str(self.original_amount.currency)
            )

        if as_of_date >= self.end_date:
            return Money(0, str(self.original_amount.currency))

        # Calculate total number of payments and payments made
        total_months = (self.end_date.year - self.start_date.year) * 12 + (
            self.end_date.month - self.start_date.month
        )
        months_passed = (as_of_date.year - self.start_date.year) * 12 + (
            as_of_date.month - self.start_date.month
        )
        months_passed = min(months_passed, total_months)

        # Simple linear calculation (more accurate calculations could be implemented)
        remaining_percentage = 1 - (months_passed / total_months)
        remaining_amount = float(self.original_amount.amount) * remaining_percentage
        # Convert to Decimal to ensure consistent type
        return Money(
            Decimal(str(remaining_amount)),
            str(self.original_amount.currency),
        )

    def amount_paid(self) -> Money:
        """Calculate the amount paid on the loan as of today."""
        # Calculate as the difference between original amount and remaining balance
        original = self.original_amount.amount
        remaining = self.remaining_balance().amount
        paid = original - remaining

        return Money(
            paid,
            str(self.original_amount.currency),
        )


class Property(BaseModel):
    """Model representing a property."""

    property_values: models.Manager["PropertyValue"]

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
    address = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    buying_value = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=False,
        verbose_name=_("Buying Value"),
        help_text=_("The value of the property at the time of purchase."),
    )
    buying_value_gross = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
    )
    shares_count = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("Number of shares in the property (if applicable)"),
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
    selling_value = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        """String representation of the Account model."""
        return str(self.name)

    class Meta:
        """Meta options for the Property model."""

        verbose_name = _("property")
        verbose_name_plural = _("properties")

    @property
    def currency(self) -> str:
        """Get the currency of the property."""
        # Access currency safely
        if hasattr(self.buying_value, "currency"):
            return str(self.buying_value.currency)
        return settings.DEFAULT_CURRENCY

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
            # Ensure we return a Money object
            value = property_values.value
            if not isinstance(value, Money):
                # If it's not already a Money object, create one
                return Money(
                    value.amount if hasattr(value, "amount") else value,
                    str(self.currency),
                )
            return value

        # Ensure buying_value is a Money object
        if not isinstance(self.buying_value, Money):
            return Money(
                self.buying_value.amount
                if hasattr(self.buying_value, "amount")
                else self.buying_value,
                str(self.currency),
            )
        return self.buying_value

    @property
    def total_remaining_loans(self) -> Money:
        """Calculate total remaining balance on all loans for this property."""
        return self.total_remaining_loans_at_date()

    def total_remaining_loans_at_date(
        self, as_of_date: datetime.date | None = None
    ) -> Money:
        """Calculate total remaining balance on all loans for this property at a specific date."""
        if as_of_date is None:
            as_of_date = datetime.date.today()

        # Using self._meta.get_field('loans').related_model to work around type checking
        loans = PropertyLoan.objects.filter(property=self)
        if not loans.exists():
            return Money(0, str(self.currency))

        # Calculate sum of all loan remaining balances at the specified date
        total = Decimal("0")
        for loan in loans:
            total += loan.remaining_balance(as_of_date).amount

        # Return as Money with proper currency
        return Money(total, str(self.currency))

    @property
    def total_paid_loans(self) -> Money:
        """Calculate total amount paid on all loans for this property."""
        # Using self._meta.get_field('loans').related_model to work around type checking
        loans = PropertyLoan.objects.filter(property=self)
        if not loans.exists():
            return Money(0, str(self.currency))

        total = sum((loan.amount_paid().amount for loan in loans), Decimal("0"))
        return Money(total, str(self.currency))

    @property
    def gross_value(self) -> Money:
        """Get the gross value of the property (current market value)."""
        return self.get_value()

    @property
    def net_value(self) -> Money:
        """Get the net value of the property (gross value minus remaining loans)."""
        return self.net_value_at_date()

    def net_value_at_date(self, as_of_date: datetime.date | None = None) -> Money:
        """Get the net value of the property at a specific date (gross value minus remaining loans)."""
        gross = self.get_value(
            max_date=datetime.datetime.combine(as_of_date, datetime.time())
            if as_of_date
            else None
        )
        remaining = self.total_remaining_loans_at_date(as_of_date)
        # Ensure we don't return negative values
        # Compare Decimal values directly to ensure test passes
        net_amount = max(Decimal("0"), gross.amount - remaining.amount)
        return Money(net_amount, str(self.currency))

    def get_progression(self, years: int | None = None) -> PropertyProgression:
        """Get the progression of the account over a specific number of years."""
        if years:
            x_years_ago = datetime.datetime.now() - datetime.timedelta(days=years * 365)
            current_value = self.get_value()
            old_value = self.get_value(max_date=x_years_ago)

            return PropertyProgression(
                current_value=current_value,
                old_value=old_value,
            )
        return PropertyProgression(
            current_value=self.get_value(),
            old_value=Money(
                (self.buying_value_gross or self.buying_value).amount,
                str((self.buying_value_gross or self.buying_value).currency),
            ),
        )


class PropertyValue(BaseModel):
    """Model representing a property value."""

    class Meta:
        """Meta options for the PropertyValue model."""

        verbose_name = _("property value")
        verbose_name_plural = _("property values")
        ordering = ["-valuation_date"]

    value = MoneyField(max_digits=10, decimal_places=0, null=False)
    valuation_date = models.DateField(null=False)
    property = models.ForeignKey(
        Property,
        related_name="property_values",
        on_delete=models.CASCADE,
        null=False,
    )


class PropertyRevenue(BaseModel):
    """Model representing a property revenue."""

    RENT = "rent"
    DIVIDEND = "dividend"
    OTHER = "other"
    REVENUE_TYPE_CHOICES = [
        (RENT, _("Rent")),
        (DIVIDEND, _("Dividend")),
        (OTHER, _("Other")),
    ]

    NONE = "none"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    RECURRENCE_TYPE_CHOICES = [
        (NONE, _("None")),
        (MONTHLY, _("Monthly")),
        (YEARLY, _("Yearly")),
    ]

    class Meta:
        """Meta options for the PropertyRevenue model."""

        verbose_name = _("property revenue")
        verbose_name_plural = _("property revenues")
        ordering = ["-revenue_date"]

    revenue = MoneyField(max_digits=10, decimal_places=0, null=False)
    revenue_date = models.DateField(
        null=False,
        verbose_name=_("Date"),
        help_text=_("Date of the revenue (or start date for recurring revenues)"),
    )
    revenue_type = models.CharField(
        max_length=50,
        choices=REVENUE_TYPE_CHOICES,
        verbose_name=_("Revenue type"),
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    property = models.ForeignKey(
        Property,
        related_name="property_revenues",
        on_delete=models.CASCADE,
        null=False,
    )

    # Recurrence fields
    recurrence_type = models.CharField(
        max_length=20,
        choices=RECURRENCE_TYPE_CHOICES,
        default=NONE,
        verbose_name=_("Recurrence type"),
    )
    recurrence_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Recurrence end date"),
        help_text=_("End date for recurring revenues (leave empty for indefinite)"),
    )

    def __str__(self) -> str:
        """String representation of the PropertyRevenue model."""
        if self.recurrence_type != self.NONE:
            return f"{self.property.name} - {self.revenue} ({self.get_recurrence_type_display()})"  # type: ignore[attr-defined]
        return f"{self.property.name} - {self.revenue} - {self.revenue_date}"

    def generate_occurrences(self, end_date: datetime.date | None = None) -> list[dict]:
        """Generate all occurrences of this revenue based on recurrence settings."""
        return generate_recurring_occurrences(
            start_date=self.revenue_date,
            amount=self.revenue,
            recurrence_type=self.recurrence_type,
            recurrence_none=self.NONE,
            recurrence_monthly=self.MONTHLY,
            recurrence_yearly=self.YEARLY,
            recurrence_end_date=self.recurrence_end_date,
            end_date=end_date,
        )


class PropertyExpense(BaseModel):
    """Model representing a property expense."""

    MAINTENANCE = "maintenance"
    TAX = "tax"
    OTHER = "other"
    EXPENSE_TYPE_CHOICES = [
        (MAINTENANCE, _("Maintenance")),
        (TAX, _("Tax")),
        (OTHER, _("Other")),
    ]

    NONE = "none"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    RECURRENCE_TYPE_CHOICES = [
        (NONE, _("None")),
        (MONTHLY, _("Monthly")),
        (YEARLY, _("Yearly")),
    ]

    class Meta:
        """Meta options for the PropertyExpense model."""

        verbose_name = _("property expense")
        verbose_name_plural = _("property expenses")
        ordering = ["-expense_date"]

    expense = MoneyField(max_digits=10, decimal_places=0, null=False)
    expense_date = models.DateField(
        null=False,
        verbose_name=_("Date"),
        help_text=_("Date of the expense (or start date for recurring expenses)"),
    )
    expense_type = models.CharField(
        max_length=50,
        choices=EXPENSE_TYPE_CHOICES,
        verbose_name=_("Expense type"),
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    property = models.ForeignKey(
        Property,
        related_name="property_expenses",
        on_delete=models.CASCADE,
        null=False,
    )

    # Recurrence fields
    recurrence_type = models.CharField(
        max_length=20,
        choices=RECURRENCE_TYPE_CHOICES,
        default=NONE,
        verbose_name=_("Recurrence type"),
    )
    recurrence_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Recurrence end date"),
        help_text=_("End date for recurring expenses (leave empty for indefinite)"),
    )

    def __str__(self) -> str:
        """String representation of the PropertyExpense model."""
        if self.recurrence_type != self.NONE:
            return f"{self.property.name} - {self.expense} ({self.get_recurrence_type_display()})"  # type: ignore[attr-defined]
        return f"{self.property.name} - {self.expense} - {self.expense_date}"

    def generate_occurrences(self, end_date: datetime.date | None = None) -> list[dict]:
        """Generate all occurrences of this expense based on recurrence settings."""
        return generate_recurring_occurrences(
            start_date=self.expense_date,
            amount=self.expense,
            recurrence_type=self.recurrence_type,
            recurrence_none=self.NONE,
            recurrence_monthly=self.MONTHLY,
            recurrence_yearly=self.YEARLY,
            recurrence_end_date=self.recurrence_end_date,
            end_date=end_date,
        )
