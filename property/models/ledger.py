"""Model for unified financial flows: PropertyLedgerEntry."""

import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField

from base.models import BaseModel
from property.utils import generate_recurring_occurrences


class PropertyLedgerEntry(BaseModel):
    """
    Unified financial flow for a property.

    - flow_type=INCOME: rent collected, charges recovered, deposit received, etc.
    - flow_type=EXPENSE: maintenance, insurance, management fees, loan interest, etc.
    - amount is always positive.
    - management_category drives both dashboard statistics and LMNP cerfa 2033-B mapping.
    """

    class FlowType(models.TextChoices):
        INCOME = "income", _("Income")
        EXPENSE = "expense", _("Expense")

    class ManagementCategory(models.TextChoices):
        """Categories for dashboard statistics and LMNP cerfa 2033-B mapping."""

        # ── Income ────────────────────────────────────────────────────────────
        RENT_COLLECTED = "rent_collected", _("Rent collected")
        CHARGES_COLLECTED = "charges_collected", _("Charges collected")
        OTHER_INCOME = "other_income", _("Other income")
        DEPOSIT_IN = "deposit_in", _("Deposit received")
        MANAGER_REVERSAL = "manager_reversal", _("Manager reversal")
        # ── Deductible expenses (LMNP réel cerfa 2033-B) ─────────────────────
        MANAGEMENT_FEES = "management_fees", _("Management fees")
        LETTING_FEES = "letting_fees", _("Letting fees")
        OTHER_GENERAL_FEES = "other_general_fees", _("Other general fees")
        COOWNERSHIP = "coownership", _("Co-ownership fees")
        MAINTENANCE = "maintenance", _("Routine maintenance")
        WORKS = "works", _("Works")
        FURNITURES = "furnitures", _("Furnitures")
        INSURANCE = "insurance", _("Insurance")
        PROPERTY_TAX = "property_tax", _("Property tax")
        CFE = "cfe", _("CFE")
        MISC_DEDUCTIBLE = "misc_deductible", _("Miscellaneous deductible")
        LOAN_INTEREST = "loan_interest", _("Loan interest")
        LOAN_INSURANCE = "loan_insurance", _("Loan insurance")
        RENTAL_GUARANTEE = "rental_guarantee", _("Rental guarantee")
        # ── Off tax result ────────────────────────────────────────────────────
        LOAN_REPAYMENT = "loan_repayment", _("Loan capital repayment")
        DEPOSIT_OUT = "deposit_out", _("Deposit returned")
        NON_DEDUCTIBLE = "non_deductible", _("Other non-deductible")
        ALUR_WORKS_FUND = "alur_works_fund", _("ALUR works fund")

    # Income categories — used in clean() to validate flow_type coherence
    _INCOME_CATEGORIES = frozenset(
        [
            ManagementCategory.RENT_COLLECTED,
            ManagementCategory.CHARGES_COLLECTED,
            ManagementCategory.OTHER_INCOME,
            ManagementCategory.DEPOSIT_IN,
            ManagementCategory.MANAGER_REVERSAL,
        ]
    )

    class RecurrenceType(models.TextChoices):
        """Recurrence type for ledger entries."""

        NONE = "none", _("None")
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")
        BIANNUAL = "biannual", _("Biannual")
        YEARLY = "yearly", _("Yearly")

    # Backward-compatible aliases (used in generate_occurrences and tests)
    NONE = RecurrenceType.NONE
    MONTHLY = RecurrenceType.MONTHLY
    QUARTERLY = RecurrenceType.QUARTERLY
    BIANNUAL = RecurrenceType.BIANNUAL
    YEARLY = RecurrenceType.YEARLY
    RECURRENCE_TYPE_CHOICES = RecurrenceType.choices

    class Meta:
        verbose_name = _("ledger entry")
        verbose_name_plural = _("ledger entries")
        ordering = ["-entry_date"]
        indexes = [
            models.Index(fields=["property", "entry_date"]),
            models.Index(fields=["property", "management_category"]),
            models.Index(fields=["flow_type", "entry_date"]),
        ]

    property = models.ForeignKey(
        "property.Property",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("Property"),
    )
    lease = models.ForeignKey(
        "property.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        verbose_name=_("Lease"),
    )
    flow_type = models.CharField(
        max_length=10,
        choices=FlowType.choices,
        verbose_name=_("Flow type"),
    )
    amount = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Amount"),
        help_text=_("Always positive. Use flow_type to indicate income or expense."),
    )
    entry_date = models.DateField(
        verbose_name=_("Date"),
        help_text=_("Date of the entry (or start date for recurring entries)."),
    )
    reference_period = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Reference period"),
        help_text=_(
            "The month/period this entry covers, e.g. first day of March 2024."
        ),
    )
    management_category = models.CharField(
        max_length=30,
        choices=ManagementCategory.choices,
        verbose_name=_("Category"),
    )
    description = models.CharField(max_length=500, blank=True)
    third_party = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Third party"),
        help_text=_("Optional. Name of the third party (tenant, supplier, etc.)."),
    )
    notes = models.TextField(blank=True)

    # Recurrence — same pattern as former PropertyRevenue/PropertyExpense
    recurrence_type = models.CharField(
        max_length=20,
        choices=RecurrenceType.choices,
        default=RecurrenceType.NONE,
        verbose_name=_("Recurrence type"),
    )
    recurrence_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Recurrence end date"),
        help_text=_("End date for recurring entries (leave empty for indefinite)."),
    )

    def __str__(self) -> str:
        name = f"{self.get_management_category_display()} — {self.amount} — {self.entry_date}"
        if self.notes:
            name += f" — {self.notes.splitlines()[0][:30]}"  # first line, max 30 chars
        if self.recurrence_type != self.NONE:
            recurrence_label = dict(self.RecurrenceType.choices).get(
                self.recurrence_type, self.recurrence_type
            )
            name += f" ({recurrence_label})"
        return name

    def clean(self) -> None:
        """Validate amount positivity and flow_type / management_category coherence."""
        if self.amount is not None and hasattr(self.amount, "amount"):
            if self.amount.amount <= 0:
                raise ValidationError({"amount": _("Amount must be positive.")})

        if self.flow_type and self.management_category:
            is_income_category = self.management_category in self._INCOME_CATEGORIES
            if self.flow_type == self.FlowType.INCOME and not is_income_category:
                raise ValidationError(
                    _(
                        "Category '%(cat)s' is not valid for an INCOME entry."
                        " Use a revenue category or set flow_type to EXPENSE."
                    )
                    % {"cat": self.management_category}
                )
            if self.flow_type == self.FlowType.EXPENSE and is_income_category:
                raise ValidationError(
                    _(
                        "Category '%(cat)s' is not valid for an EXPENSE entry."
                        " Use an expense category or set flow_type to INCOME."
                    )
                    % {"cat": self.management_category}
                )

    def get_management_category_display(self) -> str:
        return str(
            dict(PropertyLedgerEntry.ManagementCategory.choices).get(
                self.management_category, self.management_category
            )
        )

    def generate_occurrences(self, end_date: datetime.date | None = None) -> list[dict]:
        """Generate all occurrences, applying any saved exception overrides/deletions.

        Uses Django's prefetch cache when ``prefetch_related('exceptions')`` has been
        called on the queryset, otherwise falls back to one extra DB query per entry.
        Callers that do not prefetch still get correct results; prefetching is only
        needed for performance.
        """
        raw = generate_recurring_occurrences(
            start_date=self.entry_date,
            amount=self.amount,
            recurrence_type=self.recurrence_type,
            recurrence_none=self.NONE,
            recurrence_monthly=self.MONTHLY,
            recurrence_quarterly=self.QUARTERLY,
            recurrence_biannual=self.BIANNUAL,
            recurrence_yearly=self.YEARLY,
            recurrence_end_date=self.recurrence_end_date,
            end_date=end_date,
        )
        # Only look up exceptions for saved, recurring entries
        if not self.pk or self.recurrence_type == self.NONE:
            return raw

        exceptions_qs = self.exceptions.all()  # ty: ignore[unresolved-attribute]  # uses prefetch cache if available
        if not exceptions_qs:
            return raw

        exc_map = {exc.occurrence_date: exc for exc in exceptions_qs}
        result = []
        for occurrence in raw:
            exc = exc_map.get(occurrence["date"])
            if exc is None:
                result.append(occurrence)
                continue
            if exc.is_deleted:
                continue
            updated = dict(occurrence)
            if exc.amount_override is not None:
                updated["amount"] = exc.amount_override
            if exc.description_override is not None:
                updated["description_override"] = exc.description_override
            if exc.notes_override is not None:
                updated["notes_override"] = exc.notes_override
            updated["has_exception"] = True
            result.append(updated)
        return result

    def get_lmnp_line(self) -> str | None:
        """Return the cerfa 2033-B line number for this entry's category."""
        from property.services.tax_lmnp import LMNP_TAX_MAPPING

        return LMNP_TAX_MAPPING.get(self.management_category, {}).get("line")


class PropertyLedgerEntryException(BaseModel):
    """
    Override or deletion marker for a single occurrence of a recurring entry.

    - is_deleted=True: the occurrence on occurrence_date is hidden.
    - Override fields replace the parent values when set.
    """

    parent_entry = models.ForeignKey(
        PropertyLedgerEntry,
        on_delete=models.CASCADE,
        related_name="exceptions",
        verbose_name=_("Parent entry"),
    )
    occurrence_date = models.DateField(verbose_name=_("Occurrence date"))
    is_deleted = models.BooleanField(default=False, verbose_name=_("Is deleted"))
    amount_override = MoneyField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Amount override"),
    )
    description_override = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Description override"),
    )
    notes_override = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Notes override"),
    )

    class Meta:
        verbose_name = _("ledger entry exception")
        verbose_name_plural = _("ledger entry exceptions")
        unique_together = [("parent_entry", "occurrence_date")]

    def __str__(self) -> str:
        prefix = "Deleted" if self.is_deleted else "Override"
        return f"{prefix}: {self.parent_entry} @ {self.occurrence_date}"
