"""Forms for the finance app."""

from datetime import datetime

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import MoneyInputGroupMixin
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)

# CSV Import/Export choices
CSV_TYPE_CHOICES = [
    ("saving_value", _("Saving Account value")),
    ("investment_cash", _("Investment Account Cash")),
    ("investment_holding", _("Investment Account Holding")),
]


class IndexForm(forms.Form):
    """Form for the finance index view."""

    days = forms.IntegerField(
        label="Days",
        initial=30,
        min_value=1,
        help_text=_("Number of days for progression calculation."),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width: auto;"}
        ),
    )
    active_only = forms.BooleanField(
        label=_("Active accounts only"),
        required=False,
        initial=True,
        help_text=_("Show only active accounts in the index view."),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class UpdateGlobalForm(forms.Form):
    """Global form for the update view."""

    new_values_date = forms.DateTimeField(
        label=_("Date of new values"),
        required=False,  # computed in the view, not required from user input
        widget=forms.TextInput(
            attrs={"class": "form-control", "type": "datetime-local"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial value when form is instantiated, not when module is loaded
        if not self.is_bound or not self.data.get("new_values_date"):
            self.fields["new_values_date"].initial = datetime.now().strftime(
                "%Y-%m-%dT%H:%M"
            )


class BaseValueUpdateForm(forms.Form):
    """Base form for updating an account or holding value.

    Subclasses add entity-specific id/name hidden fields and any extra fields.
    Common fields: update checkbox, current_value (hidden), new_value.
    """

    update_account = forms.BooleanField(
        label=_("Update account"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    current_value = forms.DecimalField(
        max_digits=10, decimal_places=2, widget=forms.HiddenInput()
    )
    new_value = forms.DecimalField(
        label=_("New value"),
        max_digits=10,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "decimal"}),
    )


class UpdateAccountAddValueForm(BaseValueUpdateForm):
    """Form for a saving or investment cash account in the update view."""

    account_id = forms.IntegerField(widget=forms.HiddenInput())
    account_name = forms.CharField(widget=forms.HiddenInput())


# Backward-compatible aliases kept for external references.
UpdateSavingAccountAddValueForm = UpdateAccountAddValueForm
UpdateInvestmentCashAddValueForm = UpdateAccountAddValueForm


class UpdateInvestmentAccountHoldingAddValueForm(BaseValueUpdateForm):
    """Form for an account holding in the update view."""

    holding_id = forms.IntegerField(widget=forms.HiddenInput())
    holding_name = forms.CharField(widget=forms.HiddenInput())
    current_quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=4,
        label=_("Current quantity"),
        widget=forms.HiddenInput(),
        required=False,
    )
    new_quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=4,
        label=_("New quantity"),
        localize=True,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "decimal"}),
        required=False,
    )


class CSVExportForm(forms.Form):
    """Form for exporting data to CSV."""

    csv_type = forms.ChoiceField(
        label=_("Data type to export"),
        choices=CSV_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from finance.models.investment_account import InvestmentAccount
        from finance.models.saving_account import SavingAccount

        investment_accounts = InvestmentAccount.objects.filter(is_active=True)
        saving_accounts = SavingAccount.objects.filter(is_active=True)
        choices = []
        for account in investment_accounts:
            choices.append((f"investment-{account.pk}", str(account)))
        for account in saving_accounts:
            choices.append((f"saving-{account.pk}", str(account)))
        self.fields["accounts"] = forms.MultipleChoiceField(
            label=_("Accounts to export"),
            choices=choices,
            required=True,
            widget=forms.SelectMultiple(attrs={"class": "form-select"}),
        )
        self.account_groups = {
            _("Investment"): [
                (f"investment-{a.pk}", str(a)) for a in investment_accounts
            ],
            _("Saving"): [(f"saving-{a.pk}", str(a)) for a in saving_accounts],
        }


class CSVImportForm(forms.Form):
    """Form for importing data from CSV."""

    csv_type = forms.ChoiceField(
        label=_("Data type to import"),
        choices=CSV_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    csv_file = forms.FileField(
        label=_("CSV File"),
        help_text=_("Please upload a CSV file"),
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv"}),
    )


class CSVAccountMappingForm(forms.Form):
    """Form for mapping CSV account names to actual accounts."""

    csv_account_name = forms.CharField(widget=forms.HiddenInput())
    app_account_id = forms.ChoiceField(
        label=_("Map to account"),
        # choices will be set dynamically in the view
        widget=forms.Select(attrs={"class": "form-select"}),
    )


# ─── CRUD ModelForms ──────────────────────────────────────────────────────────

DATE_WIDGET = forms.DateInput(
    attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
)
DATETIME_WIDGET = forms.DateTimeInput(
    attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
)

# Common widgets shared between SavingAccountForm and InvestmentAccountForm
_COMMON_ACCOUNT_WIDGETS = {
    "name": forms.TextInput(attrs={"class": "form-control"}),
    "account_type": forms.Select(attrs={"class": "form-select"}),
    "owner": forms.TextInput(attrs={"class": "form-control"}),
    "institution": forms.TextInput(attrs={"class": "form-control"}),
    "commentaire": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    "opening_date": DATE_WIDGET,
    "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "closing_date": DATE_WIDGET,
}


class SavingAccountForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing a saving account."""

    class Meta:
        model = SavingAccount
        fields = [
            "name",
            "account_type",
            "owner",
            "institution",
            "commentaire",
            "opening_date",
            "interest_rate",
            "opening_value",
            "is_active",
            "closing_date",
        ]
        widgets = {
            **_COMMON_ACCOUNT_WIDGETS,
            "interest_rate": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
        }


class SavingAccountValueForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing a saving account value entry."""

    class Meta:
        model = SavingAccountValue
        fields = ["value", "value_date"]
        widgets = {
            "value_date": DATETIME_WIDGET,
        }


class SavingAccountDepositForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing a saving account deposit."""

    class Meta:
        model = SavingAccountDeposit
        fields = ["amount", "deposit_date", "source", "update_account_value"]
        widgets = {
            "deposit_date": DATETIME_WIDGET,
            "source": forms.TextInput(attrs={"class": "form-control"}),
            "update_account_value": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }


class InvestmentAccountForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account."""

    class Meta:
        model = InvestmentAccount
        fields = [
            "name",
            "account_type",
            "owner",
            "institution",
            "commentaire",
            "opening_date",
            "opening_cash_value",
            "is_active",
            "closing_date",
        ]
        widgets = {
            **_COMMON_ACCOUNT_WIDGETS,
        }


class InvestmentAccountHoldingForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account holding."""

    class Meta:
        model = InvestmentAccountHolding
        fields = [
            "name",
            "code",
            "isin",
            "fees",
            "issuer",
            "is_active",
            "initial_quantity",
            "initial_value",
            "initial_valuation_date",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "isin": forms.TextInput(attrs={"class": "form-control"}),
            "fees": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "issuer": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "initial_quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.0001"}
            ),
            "initial_valuation_date": DATE_WIDGET,
        }


class InvestmentAccountDepositForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account deposit."""

    class Meta:
        model = InvestmentAccountDeposit
        fields = ["amount", "deposit_date", "source", "update_account_cash"]
        widgets = {
            "deposit_date": DATE_WIDGET,
            "source": forms.TextInput(attrs={"class": "form-control"}),
            "update_account_cash": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }


class InvestmentAccountHoldingHistoryForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account holding history entry."""

    class Meta:
        model = InvestmentAccountHoldingHistory
        fields = ["value", "valuation_date", "quantity", "cash_used"]
        widgets = {
            "valuation_date": DATETIME_WIDGET,
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.0001"}
            ),
        }
