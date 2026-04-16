"""Models for property assets: Property, PropertyValue, PropertyLoan, PropertyLoanSchedule."""

import datetime
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from property.utils import (
    add_months_safe,
    PropertyProgression,
    calculate_monthly_payment,
)  # noqa: F401


class PropertyLoan(BaseModel):
    """Model representing a property loan."""

    class Meta:
        verbose_name = _("property loan")
        verbose_name_plural = _("property loans")
        ordering = ["-start_date"]

    property = models.ForeignKey(
        "property.Property",
        related_name="loans",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255, null=True, blank=True)
    lender = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Lender")
    )
    start_date = models.DateField(verbose_name=_("Start Date"))
    end_date = models.DateField(verbose_name=_("End Date"))
    original_amount = MoneyField(
        max_digits=10, decimal_places=0, verbose_name=_("Original Amount")
    )
    monthly_payment = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
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
        verbose_name=_("Monthly Insurance"),
    )

    def __str__(self) -> str:
        if self.name:
            return f"{self.property.name} - {self.name}"
        return f"{self.property.name} - {self.original_amount}"

    def is_smoothed(self) -> bool:
        """Return True if this loan uses a schedule (prêt lisseur)."""
        if not self.pk:
            return False
        return PropertyLoanSchedule.objects.filter(loan=self).exists()

    def get_duration_months(self) -> int:
        """Return the loan duration in months."""
        if self.start_date is None or self.end_date is None:
            return 0
        return (self.end_date.year - self.start_date.year) * 12 + (
            self.end_date.month - self.start_date.month
        )

    def get_payment_sequence(self) -> list[Decimal]:
        """Return the ordered list of monthly payment amounts for this loan.

        For smoothed loans (prêt lisseur), returns the full sequence derived
        from the schedules. For standard loans, returns a list of identical
        monthly_payment values of length get_duration_months().
        """
        if self.is_smoothed():
            sequence: list[Decimal] = []
            for schedule in PropertyLoanSchedule.objects.filter(loan=self).order_by(
                "order"
            ):
                sequence.extend([schedule.amount.amount] * schedule.count)
            return sequence

        duration = self.get_duration_months()
        if self.monthly_payment is None or duration <= 0:
            return []
        return [self.monthly_payment.amount] * duration

    def compute_monthly_payment(self) -> None:
        """Compute and store monthly_payment and insurance from rates and duration.

        Only applies to standard (non-smoothed) loans.
        """
        if self.is_smoothed():
            return
        duration = self.get_duration_months()
        if self.original_amount is None or self.interest_rate is None or duration <= 0:
            return
        currency = str(self.original_amount.currency)
        monthly_pi, monthly_ins, _ = calculate_monthly_payment(
            original_amount=self.original_amount.amount,
            annual_interest_rate=self.interest_rate,
            annual_insurance_rate=self.insurance_rate,
            duration_months=duration,
        )
        self.monthly_payment = Money(monthly_pi, currency)
        if self.insurance_rate:
            self.insurance = Money(monthly_ins, currency)

    def taeg_rate(self) -> Decimal:
        """Calculate the TAEG of the loan.

        For smoothed loans, returns 0 (TAEG is not meaningful with variable payments).
        """
        if self.is_smoothed():
            return Decimal("0.0")
        if (
            self.start_date is None
            or self.end_date is None
            or self.monthly_payment is None
            or self.end_date.year == self.start_date.year
        ):
            return Decimal("0.0")
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
        """Calculate the remaining balance on the loan as of a specific date.

        For smoothed loans, simulates the real amortization month by month.
        For standard loans, uses the same real amortization simulation.
        """
        from property.utils import build_loan_amortization_balance

        if as_of_date is None:
            as_of_date = datetime.date.today()

        currency = str(self.original_amount.currency)
        payment_sequence = self.get_payment_sequence()

        if self.start_date is None:
            return Money(self.original_amount.amount, currency)

        if as_of_date < self.start_date:
            return Money(self.original_amount.amount, currency)

        if payment_sequence:
            # For smoothed loans, derive the end date from the sequence length.
            # This avoids incorrect full repayment when stored end_date is stale.
            schedule_end_date = add_months_safe(self.start_date, len(payment_sequence))
            if as_of_date >= schedule_end_date:
                return Money(Decimal("0"), currency)
        elif self.end_date is not None and as_of_date >= self.end_date:
            return Money(Decimal("0"), currency)

        if not payment_sequence:
            if self.end_date is None:
                return Money(self.original_amount.amount, currency)
            # Fallback: linear approximation
            total_months = self.get_duration_months()
            months_passed = (as_of_date.year - self.start_date.year) * 12 + (
                as_of_date.month - self.start_date.month
            )
            months_passed = min(months_passed, total_months)
            remaining_percentage = 1 - (months_passed / total_months)
            remaining_amount = float(self.original_amount.amount) * remaining_percentage
            return Money(Decimal(str(remaining_amount)), currency)

        months_elapsed = (as_of_date.year - self.start_date.year) * 12 + (
            as_of_date.month - self.start_date.month
        )
        months_elapsed = min(months_elapsed, len(payment_sequence))

        balance = build_loan_amortization_balance(
            original_amount=self.original_amount.amount,
            interest_rate=self.interest_rate,
            payment_sequence=payment_sequence,
            months_elapsed=months_elapsed,
        )
        return Money(max(Decimal("0"), balance), currency)

    def amount_paid(self) -> Money:
        """Calculate the amount paid on the loan as of today."""
        paid = self.original_amount.amount - self.remaining_balance().amount
        return Money(paid, str(self.original_amount.currency))


class PropertyLoanSchedule(BaseModel):
    """A single payment tranche in a smoothed loan (prêt lisseur).

    A smoothed loan has N ordered tranches, each specifying how many consecutive
    monthly payments are made at a given amount.

    Example (PTH LISSEUR):
        order=1, count=1,   amount=1804.90 EUR
        order=2, count=118, amount=234.63  EUR
        order=3, count=1,   amount=234.82  EUR
        order=4, count=119, amount=724.39  EUR
        order=5, count=1,   amount=721.72  EUR
    """

    class Meta:
        verbose_name = _("loan schedule tranche")
        verbose_name_plural = _("loan schedule tranches")
        ordering = ["loan", "order"]
        unique_together = [("loan", "order")]

    loan = models.ForeignKey(
        PropertyLoan,
        related_name="schedules",
        on_delete=models.CASCADE,
        verbose_name=_("Loan"),
    )
    order = models.PositiveSmallIntegerField(
        verbose_name=_("Order"),
        help_text=_("Position of this tranche in the payment sequence (1 = first)."),
        validators=[MinValueValidator(1)],
    )
    count = models.PositiveIntegerField(
        verbose_name=_("Number of payments"),
        help_text=_("How many consecutive monthly payments at this amount."),
        validators=[MinValueValidator(1)],
    )
    amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Payment amount"),
        help_text=_("Monthly payment amount for this tranche (principal + interest)."),
    )

    def __str__(self) -> str:
        return f"{self.loan} — tranche {self.order}: {self.count}× {self.amount}"


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
        default=HOUSE,
        verbose_name=_("Property Type"),
    )
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    buying_value = MoneyField(
        max_digits=10,
        decimal_places=0,
        verbose_name=_("Buying Value"),
        help_text=_("The value of the property at the time of purchase."),
    )
    buying_value_gross = MoneyField(
        max_digits=10, decimal_places=0, null=True, blank=True
    )
    shares_count = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("Number of shares in the property (if applicable)"),
    )
    buying_date = models.DateField(verbose_name=_("Buying Date"))
    selling_date = models.DateField(
        null=True, blank=True, verbose_name=_("Selling Date")
    )
    selling_value = MoneyField(max_digits=10, decimal_places=0, null=True, blank=True)
    floor_area = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Floor area (m²)"),
    )
    number_of_rooms = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Number of rooms"),
    )
    is_furnished = models.BooleanField(
        default=True,
        verbose_name=_("Furnished"),
        help_text=_("Whether the property is rented furnished (LMNP meublé)."),
    )

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = _("property")
        verbose_name_plural = _("properties")

    @property
    def currency(self) -> str:
        if hasattr(self.buying_value, "currency"):
            return str(self.buying_value.currency)
        return settings.DEFAULT_CURRENCY

    @property
    def icon(self) -> str:
        """Return the icon name corresponding to the property type."""
        return {
            self.HOUSE: "house",
            self.APARTMENT: "building",
            self.CONDO: "building",
            self.LAND: "tree",
            self.OTHER: "question-circle",
        }.get(self.property_type, "building")

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
            value = property_values.value
            if not isinstance(value, Money):
                return Money(
                    value.amount if hasattr(value, "amount") else value,
                    str(self.currency),
                )
            return value

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
        return self.total_remaining_loans_at_date()

    def total_remaining_loans_at_date(
        self, as_of_date: datetime.date | None = None
    ) -> Money:
        if as_of_date is None:
            as_of_date = datetime.date.today()

        loans = PropertyLoan.objects.filter(property=self)
        if not loans.exists():
            return Money(0, str(self.currency))

        total = Decimal("0")
        for loan in loans:
            total += loan.remaining_balance(as_of_date).amount
        return Money(total, str(self.currency))

    @property
    def total_paid_loans(self) -> Money:
        loans = PropertyLoan.objects.filter(property=self)
        if not loans.exists():
            return Money(0, str(self.currency))
        total = sum((loan.amount_paid().amount for loan in loans), Decimal("0"))
        return Money(total, str(self.currency))

    @property
    def gross_value(self) -> Money:
        return self.get_value()

    @property
    def net_value(self) -> Money:
        return self.net_value_at_date()

    def net_value_at_date(self, as_of_date: datetime.date | None = None) -> Money:
        gross = self.get_value(
            max_date=datetime.datetime.combine(as_of_date, datetime.time())
            if as_of_date
            else None
        )
        remaining = self.total_remaining_loans_at_date(as_of_date)
        net_amount = max(Decimal("0"), gross.amount - remaining.amount)
        return Money(net_amount, str(self.currency))

    def get_progression(self, years: int | None = None) -> "PropertyProgression":
        if years:
            x_years_ago = datetime.datetime.now() - datetime.timedelta(days=years * 365)
            return PropertyProgression(
                current_value=self.get_value(),
                old_value=self.get_value(max_date=x_years_ago),
            )
        return PropertyProgression(
            current_value=self.get_value(),
            old_value=Money(
                (self.buying_value_gross or self.buying_value).amount,
                str((self.buying_value_gross or self.buying_value).currency),
            ),
        )


class PropertyValue(BaseModel):
    """Model representing a property valuation at a point in time."""

    class Meta:
        verbose_name = _("property value")
        verbose_name_plural = _("property values")
        ordering = ["-valuation_date"]

    value = MoneyField(max_digits=10, decimal_places=0)
    valuation_date = models.DateField()
    property = models.ForeignKey(
        Property,
        related_name="property_values",
        on_delete=models.CASCADE,
    )
