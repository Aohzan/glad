"""Forms for property management actions."""

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from property.models import (
    Lease,
    LeaseTenant,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyManager,
    PropertyValue,
    Tenant,
)
from property.utils import add_months_safe, calculate_monthly_payment


def _date_field(with_class: bool = False) -> forms.DateField:
    attrs = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_("Date"),
    )


def _recurrence_end_field(with_class: bool = False) -> forms.DateField:
    attrs = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        required=False,
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_("Recurrence End Date"),
    )


# ─── Property value ──────────────────────────────────────────────────────────


class PropertyValueQuickCreateForm(forms.ModelForm):
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


class PropertyLedgerEntryQuickCreateForm(forms.ModelForm):
    """Quick create form for ledger entries (modal on detail view)."""

    entry_date = _date_field(with_class=True)
    recurrence_end_date = _recurrence_end_field(with_class=True)

    class Meta:
        model = PropertyLedgerEntry
        fields = [
            "flow_type",
            "amount",
            "entry_date",
            "tax_category",
            "management_category",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]
        widgets = {
            "flow_type": forms.Select(
                attrs={"class": "form-select", "id": "id_flow_type"}
            ),
            "tax_category": forms.Select(
                attrs={"class": "form-select", "id": "id_tax_category"}
            ),
            "management_category": forms.Select(
                attrs={"class": "form-select", "id": "id_management_category"}
            ),
            "recurrence_type": forms.Select(
                attrs={"class": "form-select", "id": "id_recurrence_type"}
            ),
            "description": forms.TextInput(attrs={"class": "form-control"}),
        }


class PropertyLedgerEntryEditForm(forms.ModelForm):
    """Full edit form for ledger entries."""

    entry_date = _date_field(with_class=True)
    recurrence_end_date = _recurrence_end_field(with_class=True)
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
            "tax_category",
            "management_category",
            "description",
            "recurrence_type",
            "recurrence_end_date",
            "lease",
            "mandate",
            "notes",
        ]
        widgets = {
            "flow_type": forms.Select(attrs={"class": "form-select"}),
            "tax_category": forms.Select(attrs={"class": "form-select"}),
            "management_category": forms.Select(attrs={"class": "form-select"}),
            "recurrence_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "lease": forms.Select(attrs={"class": "form-select"}),
            "mandate": forms.Select(attrs={"class": "form-select"}),
        }


# ─── Property ─────────────────────────────────────────────────────────────────


class PropertyEditForm(forms.ModelForm):
    """Form for editing property details."""

    class Meta:
        model = Property
        fields = [
            "property_type",
            "name",
            "address",
            "is_active",
            "is_furnished",
            "floor_area",
            "buying_value",
            "buying_value_gross",
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


class PropertyLoanForm(forms.ModelForm):
    """Form for editing property loan details.

    The monthly_payment and insurance fields are computed automatically from
    original_amount, interest_rate, insurance_rate and duration_months.
    Users only need to enter the key loan parameters.
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
        # Make interest_rate required in the form (needed to compute monthly payment)
        self.fields["interest_rate"].required = True
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
        if commit:
            instance.save()
        return instance


# ─── Lease ────────────────────────────────────────────────────────────────────


class LeaseForm(forms.ModelForm):
    """Form for creating and editing a lease."""

    class Meta:
        model = Lease
        fields = [
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


class TenantForm(forms.ModelForm):
    """Form for creating and editing a tenant."""

    class Meta:
        model = Tenant
        fields = ["first_name", "last_name", "email", "phone", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class LeaseTenantForm(forms.ModelForm):
    """Form for linking a tenant to a lease (used in inline formset)."""

    class Meta:
        model = LeaseTenant
        fields = ["tenant", "is_primary", "join_date", "leave_date"]
        widgets = {
            "join_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "leave_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


# ─── Management ───────────────────────────────────────────────────────────────


class PropertyManagerForm(forms.ModelForm):
    """Form for creating and editing a property manager."""

    class Meta:
        model = PropertyManager
        fields = ["name", "email", "phone", "address", "siret", "notes"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class ManagementMandateForm(forms.ModelForm):
    """Form for creating and editing a management mandate."""

    class Meta:
        model = ManagementMandate
        fields = [
            "manager",
            "start_date",
            "end_date",
            "fee_type",
            "fee_percentage",
            "fixed_fee",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fee_type": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
