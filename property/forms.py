"""Forms for property management actions."""

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from base.forms import MoneyInputGroupMixin, date_field, recurrence_end_field
from property.models import (
    AmortizationAsset,
    AmortizationSetup,
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLedgerEntryException,
    PropertyLoan,
    PropertyLoanSchedule,
    PropertyValue,
)
from property.utils import add_months_safe, calculate_monthly_payment

# ─── Property value ──────────────────────────────────────────────────────────


class PropertyValueQuickCreateForm(MoneyInputGroupMixin, forms.ModelForm):
    """Quick create form for property value updates."""

    class Meta:
        model = PropertyValue
        fields = ["value", "valuation_date"]
        widgets = {
            "valuation_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }


# ─── Ledger entries (unified income + expense) ────────────────────────────────


class PropertyLedgerEntryQuickCreateForm(MoneyInputGroupMixin, forms.ModelForm):
    """Quick create form for ledger entries (modal on detail view)."""

    entry_date = date_field(with_class=True)
    recurrence_end_date = recurrence_end_field(with_class=True)

    class Meta:
        model = PropertyLedgerEntry
        fields = [
            "flow_type",
            "amount",
            "entry_date",
            "management_category",
            "lease",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]
        widgets = {
            "flow_type": forms.Select(
                attrs={"class": "form-select", "id": "id_flow_type"}
            ),
            "management_category": forms.Select(
                attrs={"class": "form-select", "id": "id_management_category"}
            ),
            "recurrence_type": forms.Select(
                attrs={"class": "form-select", "id": "id_recurrence_type"}
            ),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "lease": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, property_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        lease_field = self.fields["lease"]
        assert isinstance(lease_field, forms.ModelChoiceField)
        if property_obj is not None:
            lease_field.queryset = Lease.objects.filter(property=property_obj)
        else:
            lease_field.queryset = Lease.objects.none()
        lease_field.required = False


class PropertyLedgerEntryEditForm(MoneyInputGroupMixin, forms.ModelForm):
    """Full edit form for ledger entries."""

    entry_date = date_field(with_class=True)
    recurrence_end_date = recurrence_end_field(with_class=True)
    reference_period = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
        input_formats=["%Y-%m-%d"],
        label=_("Reference period"),
    )

    class Meta:
        model = PropertyLedgerEntry
        fields = [
            "flow_type",
            "amount",
            "entry_date",
            "reference_period",
            "management_category",
            "description",
            "recurrence_type",
            "recurrence_end_date",
            "lease",
            "notes",
        ]
        widgets = {
            "flow_type": forms.Select(attrs={"class": "form-select"}),
            "management_category": forms.Select(attrs={"class": "form-select"}),
            "recurrence_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "lease": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, property_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        lease_field = self.fields["lease"]
        assert isinstance(lease_field, forms.ModelChoiceField)
        if property_obj is not None:
            lease_field.queryset = Lease.objects.filter(property=property_obj)
        else:
            lease_field.queryset = Lease.objects.none()
        lease_field.required = False


class PropertyLedgerEntryOccurrenceForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for overriding a single occurrence of a recurring ledger entry."""

    class Meta:
        model = PropertyLedgerEntryException
        fields = ["amount_override", "description_override", "notes_override"]
        widgets = {
            "description_override": forms.TextInput(attrs={"class": "form-control"}),
            "notes_override": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_override"].required = False
        self.fields["description_override"].required = False
        self.fields["notes_override"].required = False


# ─── Property ─────────────────────────────────────────────────────────────────


class PropertyEditForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for editing property details."""

    class Meta:
        model = Property
        fields = [
            "property_type",
            "name",
            "address",
            "is_active",
            "tax_regime",
            "floor_area",
            "number_of_rooms",
            "buying_value",
            "notary_fees",
            "agency_fees",
            "other_fees",
            "credit_fees",
            "shares_count",
            "buying_date",
            "selling_date",
            "selling_value",
        ]
        widgets = {
            "buying_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "selling_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "address": forms.Textarea(attrs={"rows": 2}),
        }


class PropertyLoanForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for editing property loan details.

    For standard loans, monthly_payment and insurance are computed automatically
    from original_amount, interest_rate, insurance_rate and duration_months.

    For smoothed loans (prêt lisseur), interest_rate is optional and the payment
    schedule is managed via the PropertyLoanScheduleFormSet.
    """

    duration_months = forms.IntegerField(
        min_value=1,
        max_value=600,
        required=True,
        label=_("Duration (months)"),
        help_text=_("e.g. 240 for 20 years"),
        widget=forms.NumberInput(attrs={"placeholder": "240"}),
    )

    class Meta:
        model = PropertyLoan
        fields = [
            "name",
            "lender",
            "start_date",
            "duration_months",
            "original_amount",
            "interest_rate",
            "insurance_rate",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # interest_rate and insurance_rate are optional (default to 0)
        self.fields["interest_rate"].required = False
        self.fields["insurance_rate"].required = False
        # Pre-fill duration_months from existing instance
        if self.instance and self.instance.pk:
            duration = self.instance.get_duration_months()
            if duration:
                self.fields["duration_months"].initial = duration

    def clean(self):
        cleaned_data = super().clean() or {}
        start_date = cleaned_data.get("start_date")
        duration_months = cleaned_data.get("duration_months")
        original_amount = cleaned_data.get("original_amount")
        interest_rate = cleaned_data.get("interest_rate")
        insurance_rate = cleaned_data.get("insurance_rate")

        if start_date and duration_months:
            # Compute end_date from start_date + duration_months
            cleaned_data["end_date"] = add_months_safe(start_date, duration_months)

        # Only auto-compute monthly_payment for standard (non-smoothed) loans
        # i.e. when interest_rate is provided and no schedule exists yet
        if original_amount and interest_rate is not None and duration_months:
            monthly_pi, monthly_ins, _ = calculate_monthly_payment(
                original_amount=original_amount.amount,
                annual_interest_rate=interest_rate,
                annual_insurance_rate=insurance_rate or Decimal("0"),
                duration_months=duration_months,
            )
            currency = str(original_amount.currency)
            cleaned_data["monthly_payment"] = Money(monthly_pi, currency)
            cleaned_data["insurance"] = (
                Money(monthly_ins, currency) if insurance_rate else None
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Apply computed end_date and monthly_payment from clean()
        if "end_date" in self.cleaned_data:
            instance.end_date = self.cleaned_data["end_date"]
        if "monthly_payment" in self.cleaned_data:
            instance.monthly_payment = self.cleaned_data["monthly_payment"]
        if "insurance" in self.cleaned_data:
            instance.insurance = self.cleaned_data["insurance"]
        # insurance_rate defaults to 0 if not provided
        if instance.insurance_rate is None:
            instance.insurance_rate = Decimal("0")
        if commit:
            instance.save()
        return instance


class PropertyLoanScheduleForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for a single payment tranche of a smoothed loan (prêt lisseur)."""

    class Meta:
        model = PropertyLoanSchedule
        fields = ["order", "count", "amount"]
        widgets = {
            "order": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "placeholder": "1"}
            ),
            "count": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "placeholder": "1"}
            ),
        }


# ─── Lease ────────────────────────────────────────────────────────────────────


class LeaseForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating and editing a lease."""

    class Meta:
        model = Lease
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "lease_type",
            "status",
            "start_date",
            "end_date",
            "notice_date",
            "rent_amount",
            "charges_amount",
            "deposit_amount",
            "periodicity",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notice_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "lease_type": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "periodicity": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


# ─── Management ───────────────────────────────────────────────────────────────


class ManagementMandateForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating and editing a management mandate."""

    class Meta:
        model = ManagementMandate
        fields = [
            "manager_name",
            "manager_address",
            "manager_phone",
            "manager_email",
            "start_date",
            "end_date",
            "fee_type",
            "fee_percentage",
            "fixed_fee",
            "notes",
        ]
        widgets = {
            "manager_address": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fee_type": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class AmortizationAssetForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating and editing an amortizable asset / immobilisation (LMNP)."""

    class Meta:
        model = AmortizationAsset
        fields = [
            "label",
            "cerfa_category",
            "beginning_date",
            "value_total",
            "duration_years",
            "source_transactions",
            "notes",
        ]
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "cerfa_category": forms.Select(attrs={"class": "form-select"}),
            "beginning_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "duration_years": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "id": "id_amort_duration"}
            ),
            "source_transactions": forms.SelectMultiple(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": "3"}),
        }
        input_formats = {
            "beginning_date": ["%Y-%m-%d"],
        }

    def __init__(self, *args, property_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["source_transactions"]
        assert isinstance(field, forms.ModelMultipleChoiceField)
        field.required = False
        if property_obj is not None:
            # Works/maintenance expenses, non-recurring only.
            # M2M allows linking the same transaction to multiple assets.
            qs = PropertyLedgerEntry.objects.filter(
                property=property_obj,
                flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
                management_category__in=["works", "maintenance"],
                recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
            ).order_by("-entry_date")
            field.queryset = qs
        else:
            field.queryset = PropertyLedgerEntry.objects.none()


class AmortizationSetupForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for initialising the amortization setup of a LMNP property."""

    class Meta:
        model = AmortizationSetup
        fields = ["total_value", "land_percentage"]
        widgets = {
            "land_percentage": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                }
            ),
        }


class AmortizationInitForm(forms.Form):
    """Form for one-click amortization initialisation with optional acquisition fees."""

    extra_amount = forms.DecimalField(
        label=_("Acquisition fees to include"),
        help_text=_(
            "Additional amount to add to the purchase price for depreciation "
            "(notary fees, agency fees, miscellaneous). Set to 0 to exclude."
        ),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=12,
        initial=Decimal("0"),
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "1",
                "min": "0",
            }
        ),
    )
    land_percentage = forms.DecimalField(
        label=_("Land percentage (%)"),
        help_text=_(
            "Non-depreciable land share as a percentage of total value. Default: 15 %."
        ),
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        decimal_places=2,
        max_digits=5,
        initial=Decimal("15.00"),
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100",
            }
        ),
    )

    def clean_extra_amount(self) -> Decimal:
        value = self.cleaned_data.get("extra_amount")
        return value if value is not None else Decimal("0")

    def clean_land_percentage(self) -> Decimal:
        value = self.cleaned_data.get("land_percentage")
        return value if value is not None else Decimal("15.00")


# ─── Income & Expenses Report ────────────────────────────────────────────────


class PropertyReportFilterForm(forms.Form):
    """Filter form for the income & expenses report."""

    properties = forms.ModelMultipleChoiceField(
        queryset=Property.objects.none(),
        required=False,
        label=_("Properties"),
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )
    start_date = forms.DateField(
        required=False,
        label=_("Start date"),
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
        input_formats=["%Y-%m-%d"],
    )
    end_date = forms.DateField(
        required=False,
        label=_("End date"),
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
        input_formats=["%Y-%m-%d"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["properties"]
        assert isinstance(field, forms.ModelMultipleChoiceField)
        field.queryset = Property.objects.filter(is_active=True).order_by("name")


# ─── CSV Import ───────────────────────────────────────────────────────────────


class PropertyCSVImportForm(forms.Form):
    """Form for importing property ledger entries from a CSV file."""

    csv_file = forms.FileField(
        label=_("CSV File"),
        help_text=_(
            "Please upload a CSV file with columns: date, amount, category, description"
        ),
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv"}),
    )
