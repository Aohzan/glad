"""Forms for quick create actions on property dashboard."""

from django import forms
from django.utils.translation import gettext_lazy as _

from property.models import (
    Property,
    PropertyExpense,
    PropertyLoan,
    PropertyRevenue,
    PropertyValue,
)


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


def _date_field(with_class: bool = False) -> forms.DateField:
    attrs = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_(
            "Date"
        ),  # This label is overridden in the form classes, kept for consistency
    )


def _recurrence_end_field(with_class: bool = False) -> forms.DateField:
    attrs = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        required=False,
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_(
            "Recurrence End Date"
        ),  # This label is overridden in the form classes, kept for consistency
    )


class PropertyExpenseQuickCreateForm(forms.ModelForm):
    """Quick create form for property expenses."""

    expense_date = _date_field()
    recurrence_end_date = _recurrence_end_field()

    class Meta:
        model = PropertyExpense
        fields = [
            "expense",
            "expense_date",
            "expense_type",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]


class PropertyRevenueQuickCreateForm(forms.ModelForm):
    """Quick create form for property revenues."""

    revenue_date = _date_field()
    recurrence_end_date = _recurrence_end_field()

    class Meta:
        model = PropertyRevenue
        fields = [
            "revenue",
            "revenue_date",
            "revenue_type",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]


class PropertyExpenseEditForm(forms.ModelForm):
    """Complete edit form for property expenses."""

    expense_date = _date_field(with_class=True)
    recurrence_end_date = _recurrence_end_field(with_class=True)

    class Meta:
        model = PropertyExpense
        fields = [
            "expense",
            "expense_date",
            "expense_type",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]
        widgets = {
            "expense_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "recurrence_type": forms.Select(attrs={"class": "form-select"}),
        }


class PropertyRevenueEditForm(forms.ModelForm):
    """Complete edit form for property revenues."""

    revenue_date = _date_field(with_class=True)
    recurrence_end_date = _recurrence_end_field(with_class=True)

    class Meta:
        model = PropertyRevenue
        fields = [
            "revenue",
            "revenue_date",
            "revenue_type",
            "description",
            "recurrence_type",
            "recurrence_end_date",
        ]
        widgets = {
            "revenue_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "recurrence_type": forms.Select(attrs={"class": "form-select"}),
        }


class PropertyEditForm(forms.ModelForm):
    """Form for editing property details."""

    class Meta:
        model = Property
        fields = [
            "property_type",
            "name",
            "address",
            "is_active",
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
    """Form for editing property loan details."""

    class Meta:
        model = PropertyLoan
        fields = [
            "name",
            "lender",
            "start_date",
            "end_date",
            "original_amount",
            "monthly_payment",
            "interest_rate",
            "insurance_rate",
            "insurance",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
