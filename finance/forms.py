"""Forms for the finance app."""

from datetime import datetime

from django import forms
from django.utils.translation import gettext_lazy as _

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
        required=True,
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


class UpdateSavingAccountAddValueForm(forms.Form):
    """Form for an account in the update view."""

    account_id = forms.IntegerField(widget=forms.HiddenInput())
    account_name = forms.CharField(widget=forms.HiddenInput())
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
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class UpdateInvestmentCashAddValueForm(forms.Form):
    """Form for an investment cash account in the update view."""

    account_id = forms.IntegerField(widget=forms.HiddenInput())
    account_name = forms.CharField(widget=forms.HiddenInput())
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
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class UpdateInvestmentAccountHoldingAddValueForm(forms.Form):
    """Form for an account holding in the update view."""

    holding_id = forms.IntegerField(widget=forms.HiddenInput())
    holding_name = forms.CharField(widget=forms.HiddenInput())
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
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
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
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
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
