"""Models for property assets: Property, PropertyValue, PropertyLoan, PropertyLoanAmortizationEntry."""

import builtins
import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel
from property.services.energy import DpeStatus, get_dpe_status
from property.services.lmnp_rules import DEFAULT_COMPONENTS
from property.utils import (
    PropertyProgression,
    Schedule,
    build_schedule,
    count_installments,
    schedule_from_table,
)
from property.utils.date_utils import days360

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from property.models.lease import Lease


class PropertyLoan(BaseModel):
    """Model representing a property loan."""

    amortization_entries: RelatedManager[PropertyLoanAmortizationEntry]
    #: Last schedule built by schedule(), with the inputs it was built from.
    _schedule_memo: tuple[tuple, Schedule] | None = None

    class Meta:
        verbose_name = _("property loan")
        verbose_name_plural = _("property loans")
        ordering = ["-start_date"]

    property = models.ForeignKey(
        "property.Property",
        related_name="loans",
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Name")
    )
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
            "Date of the first bank debit, one month after the start date when"
            " empty. When it falls on another day, the interest of the first"
            " installment covers the actual number of days, as banks do."
        ),
    )

    def __str__(self) -> str:
        if self.name:
            return f"{self.property.name} - {self.name}"
        return f"{self.property.name} - {self.original_amount}"

    def get_duration_months(self) -> int:
        """Return the number of monthly installments of the loan."""
        if self.start_date is None or self.end_date is None:
            return 0
        return max(
            0,
            count_installments(self.start_date, self.first_payment_date, self.end_date),
        )

    # The ``property`` foreign key shadows the builtin in this class body.
    @builtins.property
    def currency(self) -> str:
        return str(self.original_amount.currency)

    def _monthly_insurance(self) -> Decimal:
        return self.insurance.amount if self.insurance is not None else Decimal(0)

    def _closed_on(self) -> datetime.date | None:
        """The date the loan was repaid with the sale of the property, if sold."""
        if self.property_id is None:  # ty: ignore[unresolved-attribute]
            return None
        return self.property.selling_date

    def _table_rows(
        self,
    ) -> tuple[tuple[datetime.date, Decimal, Decimal, Decimal], ...]:
        """Rows of the amortization table (prefetched when available)."""
        if self.pk is None:
            return ()
        return tuple(
            (
                entry.date,
                entry.capital.amount,
                entry.interest.amount,
                entry.remaining_balance_amount.amount,
            )
            for entry in self.amortization_entries.all()
        )

    def computed_schedule(self, closed_on: datetime.date | None = None) -> Schedule:
        """Schedule computed from the loan parameters, ignoring any table."""
        if self.start_date is None:
            return Schedule(
                capital=self.original_amount.amount,
                disbursement_date=datetime.date.min,
                installments=(),
            )
        return build_schedule(
            capital=self.original_amount.amount,
            annual_rate=self.interest_rate or Decimal(0),
            count=self.get_duration_months(),
            disbursement_date=self.start_date,
            first_payment_date=self.first_payment_date,
            monthly_payment=(
                self.monthly_payment.amount
                if self.monthly_payment is not None
                else None
            ),
            monthly_insurance=self._monthly_insurance(),
            closed_on=closed_on,
        )

    def schedule(self) -> Schedule:
        """The installments of the loan, which every loan figure derives from.

        The amortization table (imported from the bank or generated) is used
        when there is one, the loan parameters otherwise. Installments after
        the sale of the property are dropped: the loan is repaid then. The
        schedule is kept on the instance until one of its inputs changes.
        """
        rows = self._table_rows()
        closed_on = self._closed_on()
        key = (
            self.start_date,
            self.end_date,
            self.first_payment_date,
            self.original_amount.amount,
            self.interest_rate,
            self.monthly_payment.amount if self.monthly_payment is not None else None,
            self._monthly_insurance(),
            closed_on,
            rows,
        )
        if self._schedule_memo is not None and self._schedule_memo[0] == key:
            return self._schedule_memo[1]
        if rows:
            schedule = schedule_from_table(
                capital=self.original_amount.amount,
                disbursement_date=self.start_date or datetime.date.min,
                rows=rows,
                monthly_insurance=self._monthly_insurance(),
                closed_on=closed_on,
            )
        else:
            schedule = self.computed_schedule(closed_on)
        self._schedule_memo = (key, schedule)
        return schedule

    def remaining_balance(self, as_of_date: datetime.date | None = None) -> Money:
        """Capital owed at the end of *as_of_date* (today by default).

        Nothing is owed before the disbursement, nor after the sale of the
        property.
        """
        as_of_date = as_of_date or datetime.date.today()
        return Money(self.schedule().balance_at(as_of_date), self.currency)

    def amount_paid(self, as_of_date: datetime.date | None = None) -> Money:
        """Capital repaid at the end of *as_of_date* (today by default)."""
        as_of_date = as_of_date or datetime.date.today()
        if self.start_date is None or as_of_date < self.start_date:
            return Money(Decimal(0), self.currency)
        balance = self.schedule().balance_at(as_of_date)
        return Money(self.original_amount.amount - balance, self.currency)

    def interest_paid_to_date(self, as_of_date: datetime.date | None = None) -> Money:
        """Interest of the installments due up to *as_of_date* (today by default)."""
        as_of_date = as_of_date or datetime.date.today()
        return Money(self.schedule().paid_to(as_of_date).interest, self.currency)

    def insurance_paid_to_date(self, as_of_date: datetime.date | None = None) -> Money:
        """Insurance of the installments due up to *as_of_date* (today by default)."""
        as_of_date = as_of_date or datetime.date.today()
        return Money(self.schedule().paid_to(as_of_date).insurance, self.currency)


class PropertyLoanAmortizationEntry(BaseModel):
    """One row of an amortization table (bank import or auto-generated).

    Stores the exact monthly breakdown from the bank's amortization schedule.
    When entries exist, `remaining_balance()` uses them instead of auto-calculation.
    """

    class Meta:
        verbose_name = _("amortization entry")
        verbose_name_plural = _("amortization entries")
        ordering = ["date"]
        unique_together = [("loan", "date")]

    loan = models.ForeignKey(
        PropertyLoan,
        related_name="amortization_entries",
        on_delete=models.CASCADE,
        verbose_name=_("Loan"),
    )
    date = models.DateField(verbose_name=_("Payment date"))
    capital = MoneyField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Capital repaid"),
    )
    interest = MoneyField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Interest"),
    )
    remaining_balance_amount = MoneyField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Remaining balance"),
    )

    def __str__(self) -> str:
        return f"{self.loan} — {self.date}: {self.remaining_balance_amount}"


class Property(BaseModel):
    """Model representing a property."""

    property_values: RelatedManager[PropertyValue]
    leases: RelatedManager[Lease]
    loans: RelatedManager[PropertyLoan]

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
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    street_number = models.CharField(
        max_length=20, null=True, blank=True, verbose_name=_("Street number")
    )
    street_name = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Street name")
    )
    additional_address = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Additional address"),
        help_text=_("Apartment, floor, building, etc."),
    )
    postal_code = models.CharField(
        max_length=10, null=True, blank=True, verbose_name=_("Postal code")
    )
    city = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_("City")
    )
    country = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="France",
        verbose_name=_("Country"),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
    )
    insee_code = models.CharField(
        max_length=5,
        null=True,
        blank=True,
        verbose_name=_("INSEE code"),
        help_text=_("French municipality (commune) code."),
    )
    cadastral_section = models.CharField(
        max_length=10, null=True, blank=True, verbose_name=_("Cadastral section")
    )
    cadastral_parcel_number = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        verbose_name=_("Cadastral parcel number"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this property is currently owned (e.g. not sold)."),
    )
    is_favorite = models.BooleanField(
        default=False,
        verbose_name=_("Favorite"),
        help_text=_(
            "Mark this property as a favorite for quick access in the navigation menu."
        ),
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
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Shares count"),
        help_text=_("Number of shares in the property (if applicable)"),
    )
    buying_date = models.DateField(
        verbose_name=_("Buying Date"),
        help_text=_("Date of purchase of the property on the notary deed."),
    )
    selling_date = models.DateField(
        null=True, blank=True, verbose_name=_("Selling Date")
    )
    selling_value = MoneyField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name=_("Selling value"),
    )
    floor_area = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Floor area (m²)"),
        help_text=_("Carrez law surface area."),
    )
    total_surface = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Total surface (m²)"),
        help_text=_("Actual built surface, used for DVF estimation."),
    )
    number_of_rooms = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Number of rooms"),
    )

    class EnergyRating(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        E = "E", "E"
        F = "F", "F"
        G = "G", "G"

    dpe_rating = models.CharField(
        max_length=1,
        choices=EnergyRating.choices,
        blank=True,
        default="",
        verbose_name=_("Energy rating (DPE)"),
    )
    dpe_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("DPE date"),
        help_text=_("Date the energy performance diagnosis was carried out."),
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
    ownerships = GenericRelation("base.Ownership")
    lmnp_start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("LMNP activity start date"),
        help_text=_(
            "Start of the furnished rental activity under the régime réel "
            "(registration date, or 1 January of the year you switched from "
            "micro-BIC). Amortization and the first fiscal year start on the later "
            "of this date and the buying date. Leave empty to use the buying date."
        ),
    )

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = _("property")
        verbose_name_plural = _("properties")

    @property
    def amortization_start_date(self) -> datetime.date:
        """Return the date from which the property is amortized for LMNP.

        A property is amortized once it is both owned and part of the LMNP
        activity, i.e. from ``max(buying_date, lmnp_start_date)``.
        """
        if self.lmnp_start_date and self.lmnp_start_date > self.buying_date:
            return self.lmnp_start_date
        return self.buying_date

    @property
    def currency(self) -> str:
        if hasattr(self.buying_value, "currency"):
            return str(self.buying_value.currency)
        return settings.DEFAULT_CURRENCY

    @property
    def full_address(self) -> str:
        """Return the address as a single human-readable string, or empty if unset."""
        street_parts = [part for part in (self.street_number, self.street_name) if part]
        lines = []
        if street_parts:
            lines.append(" ".join(street_parts))
        if self.additional_address:
            lines.append(self.additional_address)
        city_parts = [part for part in (self.postal_code, self.city) if part]
        if city_parts:
            lines.append(" ".join(city_parts))
        if self.country and self.country != "France":
            lines.append(self.country)
        return ", ".join(lines)

    @property
    def icon(self) -> str:
        """Lucide icon name corresponding to the property type."""
        return {
            self.HOUSE: "house",
            self.APARTMENT: "building",
            self.CONDO: "building",
            self.LAND: "trees",
            self.OTHER: "circle-question-mark",
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
        total = sum(
            (loan.remaining_balance(as_of_date).amount for loan in self.loans.all()),
            Decimal(0),
        )
        return Money(total, str(self.currency))

    @property
    def total_paid_loans(self) -> Money:
        total = sum(
            (loan.amount_paid().amount for loan in self.loans.all()), Decimal(0)
        )
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
        net_amount = max(Decimal(0), gross.amount - remaining.amount)
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
        loans = self.loans.all()
        total_loans = sum(
            (
                loan.original_amount.amount
                if isinstance(loan.original_amount, Money)
                else Decimal(str(loan.original_amount or 0))
            )
            for loan in loans
        )
        return Money(self.buying_value_gross.amount - total_loans, currency)

    def get_progression(self, years: int | None = None) -> PropertyProgression:
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

    @property
    def appreciation_percent(self) -> float:
        """Return the value appreciation % versus total acquisition cost."""
        cost = self.buying_value_gross.amount
        if not cost:
            return 0.0
        return float(((self.gross_value.amount - cost) / cost) * 100)

    @property
    def loan_progress_percent(self) -> float:
        """Return the percentage of total loan capital repaid (0–100)."""
        loans = self.loans.all()
        if not loans:
            return 100.0
        total_original = sum(
            (loan.original_amount.amount for loan in loans), Decimal(0)
        )
        if not total_original:
            return 0.0
        return float((self.total_paid_loans.amount / total_original) * 100)

    @property
    def dpe_status(self) -> DpeStatus | None:
        """Rental ban and validity status of the energy rating, None without DPE."""
        return get_dpe_status(self.dpe_rating, self.dpe_date)

    @property
    def active_lease(self):
        """Return the first currently active lease, or None."""
        today = datetime.date.today()
        return (
            self.leases.filter(start_date__lte=today)
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=today))
            .first()
        )


class PropertyValue(BaseModel):
    """Model representing a property valuation at a point in time."""

    class Meta:
        verbose_name = _("property value")
        verbose_name_plural = _("property values")
        ordering = ["-valuation_date"]

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manual")
        DVF_ESTIMATE = "dvf_estimate", _("DVF estimate")

    value = MoneyField(max_digits=10, decimal_places=0)
    valuation_date = models.DateField()
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        verbose_name=_("Source"),
    )
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

    # Default LMNP component breakdown (share of total value, useful life in years).
    # Kept as a class attribute for backward compatibility; the source of truth is
    # property.services.lmnp_rules.DEFAULT_COMPONENTS.
    STANDARD_COMPONENTS: list[dict] = list(DEFAULT_COMPONENTS)

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

    def initialize_components(self) -> list[AmortizationAsset]:
        """Create the default LMNP amortization components for this setup.

        - The land component gets ``land_percentage`` of ``total_value`` and is
          never depreciated.
        - The depreciable share (``100 - land_percentage``) is split between the
          other components in proportion to their default shares.
        - Amortization starts when the property is both owned and part of the
          LMNP activity: ``max(buying_date, lmnp_start_date)``.

        Existing initial components are deleted before new ones are created.
        """
        AmortizationAsset.objects.filter(
            property=self.property, is_initial_component=True
        ).delete()

        currency = str(self.total_value.currency)
        total = self.total_value.amount
        beginning_date = self.property.amortization_start_date
        cents = Decimal("0.01")

        land_share = self.land_percentage / Decimal(100)
        depreciable_components = [c for c in DEFAULT_COMPONENTS if c["duration"]]
        depreciable_pct_sum = sum(Decimal(c["pct"]) for c in depreciable_components)

        values: dict[str, Decimal] = {}
        for comp in depreciable_components:
            share = (1 - land_share) * Decimal(comp["pct"]) / depreciable_pct_sum
            values[comp["label"]] = (total * share).quantize(cents)
        # Land takes the remainder so that the components add up exactly to the total.
        land_value = total - sum(values.values(), Decimal(0))

        created: list[AmortizationAsset] = []
        for comp in DEFAULT_COMPONENTS:
            value = land_value if comp["duration"] is None else values[comp["label"]]
            asset = AmortizationAsset(
                property=self.property,
                label=comp["label"],
                beginning_date=beginning_date,
                value_total=Money(value, currency),
                duration_years=comp["duration"],
                is_initial_component=True,
                cerfa_category=comp["cerfa_category"],
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
        help_text=_(
            "Amortization duration in years. Leave blank for non-depreciable assets (e.g. land)."
        ),
        null=True,
        blank=True,
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

    @builtins.property
    def is_depreciable(self) -> bool:
        """Return True if this asset can be depreciated (i.e. not land)."""
        return (
            self.cerfa_category != self.CerfaCategory.TERRAINS
            and self.duration_years is not None
        )

    def depreciable_base(self) -> Money:
        """Return the depreciable base of this asset.

        The land share is already excluded at the AmortizationSetup level when
        computing component values, so the full value_total is depreciable here.
        """
        return Money(self.value_total.amount, str(self.value_total.currency))

    @builtins.property
    def amortization_end_year(self) -> int | None:
        """Return the last year in which a dotation is recorded, or None.

        An asset acquired on 1 January is fully amortized after exactly
        ``duration_years`` years. Any other start date adds one more year that
        carries the remainder of the first-year prorata.
        """
        if (
            not self.beginning_date
            or not self.duration_years
            or not self.is_depreciable
        ):
            return None
        starts_on_january_first = (
            self.beginning_date.month == 1 and self.beginning_date.day == 1
        )
        return (
            self.beginning_date.year
            + self.duration_years
            - (1 if starts_on_january_first else 0)
        )

    def get_annual_amortization(self, year: int) -> Decimal:
        """Return the linear amortization dotation (2033-C line 572) for a year.

        Formula, identical to the reference LMNP workbook:
          - first year:  ``value / (duration × 360) × DAYS360(start, 31/12)``
            (prorata temporis on a 30/360 basis);
          - full years:  ``value / duration``;
          - last year:   ``value − Σ previous dotations`` (the remainder, so that
            the dotations add up exactly to the depreciable base).

        Returns ``Decimal("0")`` outside the asset's useful life or for land.
        """
        end_year = self.amortization_end_year
        if end_year is None or self.beginning_date is None or not self.duration_years:
            return Decimal(0)

        start_year = self.beginning_date.year
        if year < start_year or year > end_year:
            return Decimal(0)

        base = self.depreciable_base().amount
        cents = Decimal("0.01")
        annual = base / Decimal(self.duration_years)

        if year == end_year:
            already_amortized = sum(
                (self.get_annual_amortization(y) for y in range(start_year, year)),
                Decimal(0),
            )
            return max(Decimal(0), base - already_amortized).quantize(cents)

        if year == start_year:
            days = days360(self.beginning_date, datetime.date(start_year, 12, 31))
            return (annual * Decimal(days) / Decimal(360)).quantize(cents)

        return annual.quantize(cents)

    def cumulative_amortization(self, up_to_year: int) -> Decimal:
        """Return the sum of all annual amortizations from acquisition year to *up_to_year* (inclusive)."""
        if not self.beginning_date:
            return Decimal(0)
        return sum(
            (
                self.get_annual_amortization(y)
                for y in range(self.beginning_date.year, up_to_year + 1)
            ),
            Decimal(0),
        )
