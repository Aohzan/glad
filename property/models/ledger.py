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
    Unified financial flow for a property (replaces PropertyRevenue + PropertyExpense).

    - flow_type=INCOME: rent collected, charges recovered, deposit received, etc.
    - flow_type=EXPENSE: maintenance, insurance, management fees, loan interest, etc.
    - amount is always positive.
    - tax_category maps to LMNP réel cerfa 2033-B lines.
      The TaxCategory choices are designed to be extensible for other tax regimes
      (micro-BIC, SCI IS, etc.) by adding new choices without breaking existing data.
    """

    class FlowType(models.TextChoices):
        INCOME = "income", _("Income")
        EXPENSE = "expense", _("Expense")

    class TaxCategory(models.TextChoices):
        # ── Recettes ──────────────────────────────────────────────────────────
        RENT = "rent", _("Rent")
        CHARGES_RECOVERED = "charges_recovered", _("Recovered charges")
        OTHER_INCOME = "other_income", _("Other income")
        # ── Charges déductibles LMNP réel (cerfa 2033-B) ─────────────────────
        MANAGEMENT_FEES = "management_fees", _("Management fees (l.218)")
        OTHER_GENERAL_FEES = "other_general_fees", _("Other general fees (l.220)")
        MAINTENANCE_REPAIRS = "maintenance_repairs", _("Maintenance & repairs (l.222)")
        INSURANCE = "insurance", _("Insurance premiums (l.224)")
        TAXES = "taxes", _("Taxes — property tax, CFE (l.226)")
        MISC_DEDUCTIBLE = "misc_deductible", _("Miscellaneous deductible (l.228)")
        LOAN_INTEREST = "loan_interest", _("Loan interest (l.230)")
        # ── Hors résultat fiscal ──────────────────────────────────────────────
        LOAN_REPAYMENT = "loan_repayment", _("Loan capital repayment (non-deductible)")
        DEPOSIT_IN = "deposit_in", _("Security deposit received")
        DEPOSIT_OUT = "deposit_out", _("Security deposit returned")
        NON_DEDUCTIBLE = "non_deductible", _("Other non-deductible")

    # Income categories — used in clean() to validate flow_type coherence
    _INCOME_CATEGORIES = frozenset(
        [
            TaxCategory.RENT,
            TaxCategory.CHARGES_RECOVERED,
            TaxCategory.OTHER_INCOME,
            TaxCategory.DEPOSIT_IN,
        ]
    )

    class ManagementCategory(models.TextChoices):
        """Internal management categories for dashboard statistics."""

        RENT_COLLECTED = "rent_collected", _("Rent collected")
        CHARGES_COLLECTED = "charges_collected", _("Charges collected")
        DEPOSIT_IN = "deposit_in", _("Deposit received")
        DEPOSIT_OUT = "deposit_out", _("Deposit returned")
        MANAGER_REVERSAL = "manager_reversal", _("Manager reversal")
        MAINTENANCE = "maintenance", _("Routine maintenance")
        WORKS = "works", _("Works")
        INSURANCE = "insurance", _("Insurance")
        COOWNERSHIP = "coownership", _("Co-ownership fees")
        MANAGEMENT_FEES = "management_fees", _("Management fees")
        LOAN_INTEREST = "loan_interest", _("Loan interest")
        LOAN_INSURANCE = "loan_insurance", _("Loan insurance")
        PROPERTY_TAX = "property_tax", _("Property tax")
        CFE = "cfe", _("CFE")
        OTHER = "other", _("Other")

    class RecurrenceType(models.TextChoices):
        """Recurrence type for ledger entries."""

        NONE = "none", _("None")
        MONTHLY = "monthly", _("Monthly")
        YEARLY = "yearly", _("Yearly")

    # Backward-compatible aliases (used in generate_occurrences and tests)
    NONE = RecurrenceType.NONE
    MONTHLY = RecurrenceType.MONTHLY
    YEARLY = RecurrenceType.YEARLY
    RECURRENCE_TYPE_CHOICES = RecurrenceType.choices

    class Meta:
        verbose_name = _("ledger entry")
        verbose_name_plural = _("ledger entries")
        ordering = ["-entry_date"]
        indexes = [
            models.Index(fields=["property", "entry_date"]),
            models.Index(fields=["property", "tax_category"]),
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
    mandate = models.ForeignKey(
        "property.ManagementMandate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        verbose_name=_("Management mandate"),
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
    tax_category = models.CharField(
        max_length=30,
        choices=TaxCategory.choices,
        verbose_name=_("Tax category"),
    )
    management_category = models.CharField(
        max_length=30,
        choices=ManagementCategory.choices,
        verbose_name=_("Management category"),
    )
    description = models.CharField(max_length=500, blank=True)
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
        if self.recurrence_type != self.NONE:
            recurrence_label = dict(self.RecurrenceType.choices).get(
                self.recurrence_type, self.recurrence_type
            )
            return f"{self.property.name} — {self.amount} ({recurrence_label})"
        return f"{self.property.name} — {self.amount} — {self.entry_date}"

    def clean(self) -> None:
        """Validate amount positivity and flow_type / tax_category coherence."""
        if self.amount is not None and hasattr(self.amount, "amount"):
            if self.amount.amount <= 0:
                raise ValidationError({"amount": _("Amount must be positive.")})

        if self.flow_type and self.tax_category:
            is_income_category = self.tax_category in self._INCOME_CATEGORIES
            if self.flow_type == self.FlowType.INCOME and not is_income_category:
                raise ValidationError(
                    _(
                        "Tax category '%(cat)s' is not valid for an INCOME entry."
                        " Use a revenue category or set flow_type to EXPENSE."
                    )
                    % {"cat": self.tax_category}
                )
            if self.flow_type == self.FlowType.EXPENSE and is_income_category:
                raise ValidationError(
                    _(
                        "Tax category '%(cat)s' is not valid for an EXPENSE entry."
                        " Use an expense category or set flow_type to INCOME."
                    )
                    % {"cat": self.tax_category}
                )

    def get_tax_category_display(self) -> str:
        return str(
            dict(PropertyLedgerEntry.TaxCategory.choices).get(
                self.tax_category, self.tax_category
            )
        )

    def get_management_category_display(self) -> str:
        return str(
            dict(PropertyLedgerEntry.ManagementCategory.choices).get(
                self.management_category, self.management_category
            )
        )

    def generate_occurrences(self, end_date: datetime.date | None = None) -> list[dict]:
        """Generate all occurrences of this entry based on recurrence settings."""
        return generate_recurring_occurrences(
            start_date=self.entry_date,
            amount=self.amount,
            recurrence_type=self.recurrence_type,
            recurrence_none=self.NONE,
            recurrence_monthly=self.MONTHLY,
            recurrence_yearly=self.YEARLY,
            recurrence_end_date=self.recurrence_end_date,
            end_date=end_date,
        )

    def get_lmnp_line(self) -> str | None:
        """Return the cerfa 2033-B line number for this entry's tax category."""
        from property.services.tax_lmnp import LMNP_TAX_MAPPING

        return LMNP_TAX_MAPPING.get(self.tax_category, {}).get("line")
