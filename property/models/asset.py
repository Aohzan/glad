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
    PropertyProgression,
    add_months_safe,  # noqa: F401
    calculate_monthly_payment,
)


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
        default=Decimal("0.0"),
        verbose_name=_("Interest Rate"),
    )
    insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Insurance Rate"),
    )
    insurance = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Monthly Insurance"),
    )
    bank_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Bank reference"),
        help_text=_("Loan reference number as shown on your bank statements."),
    )
    first_payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("First payment date"),
        help_text=_(
            "Date of the first bank debit. When set, the first month's interest is"
            " calculated proportionally based on the actual number of days between"
            " the disbursement date and the first payment, matching the bank's"
            " amortization table."
        ),
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
            disbursement_date=self.start_date,
            first_payment_date=self.first_payment_date,
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


class PropertyLoanAnnualStatement(BaseModel):
    """Annual statement of loan interest and insurance provided by the bank.

    When present for a given loan and year, these amounts are used in the LMNP
    tax declaration (cerfa 2033-B line 294) and in cashflow charts instead of
    the computed values, to match the exact figures from the bank.
    """

    class Meta:
        verbose_name = _("annual loan statement")
        verbose_name_plural = _("annual loan statements")
        ordering = ["-year"]
        unique_together = [("loan", "year")]

    loan = models.ForeignKey(
        PropertyLoan,
        related_name="annual_statements",
        on_delete=models.CASCADE,
        verbose_name=_("Loan"),
    )
    year = models.PositiveIntegerField(verbose_name=_("Year"))
    interest_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Interest paid"),
        help_text=_("Total interest paid during the year as stated by the bank."),
    )
    insurance_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Insurance paid"),
        help_text=_(
            "Total insurance premium paid during the year as stated by the bank."
        ),
    )

    def __str__(self) -> str:
        return f"{self.loan} — {self.year}"


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
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this property is currently owned (e.g. not sold)."),
    )
    buying_value = MoneyField(
        max_digits=10,
        decimal_places=0,
        verbose_name=_("Buying Value"),
        help_text=_("Purchase price of the property, excluding fees."),
    )
    notary_fees = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name=_("Notary fees"),
        help_text=_("Notary fees paid at the time of purchase."),
    )
    agency_fees = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name=_("Agency fees"),
        help_text=_("Intermediary fees (agencies, headhunters, etc.)."),
    )
    other_fees = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name=_("Other fees"),
        help_text=_("Any other fees paid at the time of purchase."),
    )
    credit_fees = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name=_("Credit fees"),
        help_text=_("Loan arrangement and guarantee fees (excluding interest)."),
    )
    coproperty_share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Coproperty share (%)"),
        help_text=_("Share of the coproperty (in %), if applicable."),
    )
    shares_count = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("Number of shares in the property (if applicable)"),
    )
    buying_date = models.DateField(
        verbose_name=_("Buying Date"),
        help_text=_("Date of purchase of the property on the notary deed."),
    )
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

    class TaxRegime(models.TextChoices):
        NONE = "none", _("None")
        LMNP_REEL = "lmnp_reel", _("LMNP réel")

    tax_regime = models.CharField(
        max_length=20,
        choices=TaxRegime.choices,
        default=TaxRegime.NONE,
        verbose_name=_("Tax regime"),
        help_text=_("Tax regime applicable to this property (e.g. LMNP réel)."),
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

    @property
    def buying_value_gross(self) -> Money:
        """Total acquisition cost: purchase price plus all ancillary fees."""
        currency = str(self.currency)
        total = (
            self.buying_value.amount
            if isinstance(self.buying_value, Money)
            else Decimal(str(self.buying_value or 0))
        )
        for fee_field in (
            self.notary_fees,
            self.agency_fees,
            self.other_fees,
            self.credit_fees,
        ):
            if fee_field is not None:
                total += (
                    fee_field.amount
                    if isinstance(fee_field, Money)
                    else Decimal(str(fee_field))
                )
        return Money(total, currency)

    @property
    def cash_deposit(self) -> Money:
        """Cash contribution at purchase time: gross cost minus all loan amounts."""
        currency = str(self.currency)
        loans = PropertyLoan.objects.filter(property=self)
        total_loans = sum(
            (
                loan.original_amount.amount
                if isinstance(loan.original_amount, Money)
                else Decimal(str(loan.original_amount or 0))
            )
            for loan in loans
        )
        return Money(self.buying_value_gross.amount - total_loans, currency)

    def get_progression(self, years: int | None = None) -> "PropertyProgression":
        if years:
            x_years_ago = datetime.datetime.now() - datetime.timedelta(days=years * 365)
            return PropertyProgression(
                current_value=self.get_value(),
                old_value=self.get_value(max_date=x_years_ago),
            )
        return PropertyProgression(
            current_value=self.get_value(),
            old_value=self.buying_value_gross,
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


class AmortizationSetup(BaseModel):
    """
    One-time amortization initialisation parameters for a LMNP réel property.

    Stores the total value to depreciate and the land percentage, then creates
    the standard components automatically via ``initialize_components()``.
    """

    # Standard LMNP component breakdown (% of total value, duration in years).
    # The remaining land_percentage (default 15 %) is never depreciable.
    STANDARD_COMPONENTS: list[dict] = [
        {
            "label": "Gros œuvre",
            "pct": 45,
            "duration": 75,
            "cerfa_category": "constructions",
        },
        {
            "label": "Installations électriques",
            "pct": 6,
            "duration": 30,
            "cerfa_category": "installations",
        },
        {
            "label": "Étanchéité",
            "pct": 7,
            "duration": 25,
            "cerfa_category": "constructions",
        },
        {
            "label": "Toiture",
            "pct": 8,
            "duration": 25,
            "cerfa_category": "constructions",
        },
        {
            "label": "Agencements intérieurs",
            "pct": 19,
            "duration": 12,
            "cerfa_category": "autres",
        },
    ]

    class Meta:
        verbose_name = _("amortization setup")
        verbose_name_plural = _("amortization setups")

    property = models.OneToOneField(
        "property.Property",
        on_delete=models.CASCADE,
        related_name="amortization_setup",
        verbose_name=_("Property"),
    )
    total_value = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Total value to depreciate"),
        help_text=_(
            "Total acquisition value used as the base for depreciation (excl. land)."
        ),
    )
    land_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("15.00"),
        verbose_name=_("Land percentage (%)"),
        help_text=_(
            "Non-depreciable land share as a percentage of total value. Default: 15 %."
        ),
    )

    def __str__(self) -> str:
        return f"{self.property.name} — amortization setup"

    def initialize_components(self) -> list["AmortizationAsset"]:
        """Create the standard LMNP amortization components for this setup.

        Uses the property buying_date as beginning_date.  Only the
        depreciable share (100 - land_percentage) is split across components.
        Existing initial components are deleted before new ones are created.
        """
        AmortizationAsset.objects.filter(
            property=self.property, is_initial_component=True
        ).delete()

        currency = str(self.total_value.currency)
        buying_date = self.property.buying_date
        created: list[AmortizationAsset] = []

        for comp in self.STANDARD_COMPONENTS:
            # pct is % of total property value (land + bâti)
            component_value = (
                self.total_value.amount * Decimal(str(comp["pct"])) / Decimal("100")
            )
            asset = AmortizationAsset(
                property=self.property,
                label=comp["label"],
                beginning_date=buying_date,
                value_total=Money(component_value.quantize(Decimal("0.01")), currency),
                duration_years=comp["duration"],
                is_initial_component=True,
                cerfa_category=comp.get("cerfa_category", ""),
            )
            asset.save()
            created.append(asset)
        return created


class AmortizationAsset(BaseModel):
    """
    An amortizable asset component (immobilisation) attached to a property.

    LMNP réel requires splitting the property into depreciable components.
    The standard components are created automatically via AmortizationSetup.
    Additional items (e.g. new appliances or renovation) can be added manually
    (``is_initial_component=False``).

    Amortization is linear with prorata temporis in the first and last year
    (month-based, standard LMNP practice).
    """

    class Meta:
        verbose_name = _("immobilisation")
        verbose_name_plural = _("immobilisations")
        ordering = ["label"]
        indexes = [
            models.Index(fields=["property", "beginning_date"]),
        ]

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="amortization_assets",
        verbose_name=_("Property"),
    )
    label = models.CharField(
        max_length=255,
        verbose_name=_("Label"),
        help_text=_("Description of the asset, e.g. 'Toiture', 'Cuisine équipée'."),
    )
    beginning_date = models.DateField(
        verbose_name=_("Beginning date"),
        help_text=_("Date of the beginning of the asset's useful life."),
    )
    value_total = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Total value"),
        help_text=_(
            "Total acquisition value of this asset (including VAT if applicable)."
        ),
    )
    duration_years = models.PositiveIntegerField(
        verbose_name=_("Duration (years)"),
        help_text=_("Amortization duration in years."),
        validators=[MinValueValidator(1)],
    )
    is_initial_component = models.BooleanField(
        default=False,
        verbose_name=_("Initial component"),
        help_text=_(
            "Set automatically when created by the standard amortization setup."
        ),
    )

    class CerfaCategory(models.TextChoices):
        TERRAINS = "terrains", _("Terrains")
        CONSTRUCTIONS = "constructions", _("Constructions")
        INSTALLATIONS = "installations", _("Installations générales")
        AUTRES = "autres", _("Autres immobilisations corporelles")

    cerfa_category = models.CharField(
        max_length=20,
        choices=CerfaCategory.choices,
        blank=True,
        default="",
        verbose_name=_("Cerfa 2033-C category"),
        help_text=_(
            "Asset category for cerfa 2033-C: terrains, constructions, "
            "installations générales, or autres immobilisations corporelles."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes"),
        help_text=_("Optional free-text notes about this asset."),
    )
    source_transactions = models.ManyToManyField(
        "property.PropertyLedgerEntry",
        blank=True,
        related_name="capitalized_as",
        verbose_name=_("Source transactions"),
        help_text=_(
            "Ledger entries recording the payment(s) for this asset. "
            "Linked transactions are excluded from deductible charges to avoid double-counting."
        ),
    )

    def __str__(self) -> str:
        return f"{self.property.name} — {self.label}"

    def depreciable_base(self) -> Money:
        """Return the depreciable base of this asset.

        The land share is already excluded at the AmortizationSetup level when
        computing component values, so the full value_total is depreciable here.
        """
        return Money(self.value_total.amount, str(self.value_total.currency))

    def get_annual_amortization(self, year: int) -> Decimal:
        """Return the linear amortization dotation for a given fiscal year.

        Applies prorata temporis (month-based) in the first year of acquisition
        and in the last year.  Returns Decimal("0") for years outside the
        asset's useful life.
        """
        if self.beginning_date is None or self.duration_years is None:
            return Decimal("0")

        start_year = self.beginning_date.year
        end_year = (
            start_year + self.duration_years
        )  # exclusive: fully amortized at start of end_year

        if year < start_year or year >= end_year:
            return Decimal("0")

        base = self.depreciable_base().amount
        if self.duration_years == 0:
            return Decimal("0")
        annual = base / Decimal(self.duration_years)

        if year == start_year and year == end_year - 1:
            # Single-year asset: prorata = months in service / 12
            months_in_service = Decimal(13 - self.beginning_date.month)
            return (annual * months_in_service / Decimal("12")).quantize(
                Decimal("0.01")
            )

        if year == start_year:
            # First year: prorata temporis from acquisition month
            # Convention: month of acquisition counts as full month
            months_in_service = Decimal(13 - self.beginning_date.month)
            return (annual * months_in_service / Decimal("12")).quantize(
                Decimal("0.01")
            )

        if year == end_year - 1:
            # Last year: complement of first-year prorata
            months_first_year = Decimal(13 - self.beginning_date.month)
            months_last_year = Decimal("12") - months_first_year
            if months_last_year <= Decimal("0"):
                return Decimal("0")
            return (annual * months_last_year / Decimal("12")).quantize(Decimal("0.01"))

        return annual.quantize(Decimal("0.01"))

    def cumulative_amortization(self, up_to_year: int) -> Decimal:
        """Return the sum of all annual amortizations from acquisition year to up_to_year (inclusive)."""
        if self.beginning_date is None:
            return Decimal("0")
        total = Decimal("0")
        for y in range(self.beginning_date.year, up_to_year + 1):
            total += self.get_annual_amortization(y)
        return total
