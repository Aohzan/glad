"""Forms for the finance app."""

from datetime import datetime
from typing import cast

from django import forms
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from base.forms import MoneyInputGroupMixin, OwnersFormMixin
from base.widgets import SuggestionsTextInput
from finance.models.investment_account import (
    EuroFundRate,
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from property.models import PropertyLoan

# Fields holding a bank name: suggest the same spellings on accounts and loans.
INSTITUTION_SOURCES = (
    (SavingAccount, "institution"),
    (InvestmentAccount, "institution"),
    (PropertyLoan, "lender"),
)
DEPOSIT_SOURCE_SOURCES = (
    (SavingAccountDeposit, "source"),
    (InvestmentAccountDeposit, "source"),
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
        max_digits=16,
        decimal_places=6,
        label=_("Current quantity"),
        widget=forms.HiddenInput(),
        required=False,
    )
    new_quantity = forms.DecimalField(
        max_digits=16,
        decimal_places=6,
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
    "institution": SuggestionsTextInput(
        INSTITUTION_SOURCES, attrs={"class": "form-control"}
    ),
    "commentaire": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    "opening_date": DATE_WIDGET,
    "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "closing_date": DATE_WIDGET,
}


class AddToPreviousValueMixin:
    """Let a new value entry be typed as an amount added to the previous value.

    On creation, the form gains an optional ``amount_to_add`` field. When it is
    filled instead of ``value``, the saved value is the parent's value at the
    entry date plus that amount. Apply it before ``forms.ModelForm``.
    """

    parent_field = "account"
    date_field = "value_date"
    # Method of the parent returning its value at a given date.
    value_at = "get_value"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form = cast(forms.ModelForm, self)
        instance = form.instance
        if (
            instance.pk is not None
            or getattr(instance, f"{self.parent_field}_id") is None
        ):
            return
        form.fields["value"].required = False
        form.fields["amount_to_add"] = forms.DecimalField(
            label=_("Or amount to add"),
            required=False,
            max_digits=12,
            decimal_places=2,
            localize=True,
            help_text=_(
                "Added to the previous value at the chosen date. "
                "Use a negative amount to subtract."
            ),
            widget=forms.TextInput(
                attrs={"class": "form-control", "inputmode": "decimal"}
            ),
        )

    def clean(self):
        form = cast(forms.ModelForm, self)
        cleaned_data = super().clean() or {}  # ty: ignore[unresolved-attribute]
        if "amount_to_add" not in form.fields:
            return cleaned_data
        amount = cleaned_data.get("amount_to_add")
        has_value = cleaned_data.get("value") is not None
        if amount is None:
            if not has_value and "value" not in form.errors:
                form.add_error("value", form.fields["value"].error_messages["required"])
            return cleaned_data
        if has_value:
            form.add_error(
                "amount_to_add",
                _("Fill in either the new value or the amount to add, not both."),
            )
            return cleaned_data
        when = cleaned_data.get(self.date_field)
        if when is not None:
            parent = getattr(form.instance, self.parent_field)
            previous: Money = getattr(parent, self.value_at)(when)
            cleaned_data["value"] = previous + Money(amount, previous.currency)
        return cleaned_data


class SavingAccountForm(MoneyInputGroupMixin, OwnersFormMixin, forms.ModelForm):
    """Form for creating/editing a saving account."""

    class Meta:
        model = SavingAccount
        fields = [
            "name",
            "account_type",
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


class SavingAccountValueForm(
    AddToPreviousValueMixin, MoneyInputGroupMixin, forms.ModelForm
):
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
            "source": SuggestionsTextInput(
                DEPOSIT_SOURCE_SOURCES, attrs={"class": "form-control"}
            ),
            "update_account_value": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }


class InvestmentAccountForm(MoneyInputGroupMixin, OwnersFormMixin, forms.ModelForm):
    """Form for creating/editing an investment account."""

    class Meta:
        model = InvestmentAccount
        fields = [
            "name",
            "account_type",
            "institution",
            "commentaire",
            "opening_date",
            "opening_cash_value",
            "benchmark_symbol",
            "is_active",
            "closing_date",
        ]
        widgets = {
            **_COMMON_ACCOUNT_WIDGETS,
            "benchmark_symbol": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "CW8.PA"}
            ),
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
            "asset_class",
            "is_active",
            "initial_quantity",
            "initial_value",
            "initial_valuation_date",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "isin": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _(
                        "e.g. FR0010315770 — Autofill will fetch code, "
                        "name, issuer, fees & initial value"
                    ),
                }
            ),
            "fees": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "issuer": SuggestionsTextInput(
                [(InvestmentAccountHolding, "issuer")], attrs={"class": "form-control"}
            ),
            "asset_class": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "initial_quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.000001"}
            ),
            "initial_valuation_date": DATE_WIDGET,
        }


class InvestmentAccountCashForm(
    AddToPreviousValueMixin, MoneyInputGroupMixin, forms.ModelForm
):
    """Form for creating/editing an investment account cash entry."""

    value_at = "get_cash_value"

    class Meta:
        model = InvestmentAccountCash
        fields = ["value", "value_date"]
        widgets = {
            "value_date": DATE_WIDGET,
        }


class InvestmentAccountDepositForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account deposit."""

    class Meta:
        model = InvestmentAccountDeposit
        fields = ["amount", "deposit_date", "source", "update_account_cash"]
        widgets = {
            "deposit_date": DATE_WIDGET,
            "source": SuggestionsTextInput(
                DEPOSIT_SOURCE_SOURCES, attrs={"class": "form-control"}
            ),
            "update_account_cash": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.fields["update_account_cash"].initial = False


class InvestmentAccountHoldingHistoryForm(MoneyInputGroupMixin, forms.ModelForm):
    """Form for creating/editing an investment account holding history entry."""

    class Meta:
        model = InvestmentAccountHoldingHistory
        fields = ["value", "valuation_date", "quantity", "cash_used"]
        widgets = {
            "valuation_date": DATETIME_WIDGET,
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.000001"}
            ),
        }


BACKFILL_MAX_RANGE_YEARS = 10


class BackfillHoldingHistoryForm(forms.Form):
    """Form to pick a date range to fill missing monthly history entries."""

    start_date = forms.DateField(
        label=_("Start date"), widget=DATE_WIDGET, input_formats=["%Y-%m-%d"]
    )
    end_date = forms.DateField(
        label=_("End date"), widget=DATE_WIDGET, input_formats=["%Y-%m-%d"]
    )

    def clean(self):
        cleaned_data = super().clean() or {}
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError(
                    _("Start date must be before the end date.")
                )
            if (end_date - start_date).days > BACKFILL_MAX_RANGE_YEARS * 366:
                raise forms.ValidationError(
                    _("The date range cannot exceed {years} years.").format(
                        years=BACKFILL_MAX_RANGE_YEARS
                    )
                )
        return cleaned_data


class OtherAssetForm(MoneyInputGroupMixin, OwnersFormMixin, forms.ModelForm):
    """Form for creating/editing an other asset."""

    owners_after = "category"

    class Meta:
        model = OtherAsset
        fields = [
            "name",
            "category",
            "acquisition_date",
            "acquisition_value",
            "quantity",
            "ticker",
            "liquidity",
            "is_active",
            "sold_date",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "acquisition_date": DATE_WIDGET,
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.00000001"}
            ),
            "ticker": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "BTC-EUR"}
            ),
            "liquidity": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sold_date": DATE_WIDGET,
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned = super().clean() or {}
        # The history values an asset until its sale date: an asset that is no
        # longer held needs one.
        if not cleaned.get("is_active") and not cleaned.get("sold_date"):
            self.add_error("sold_date", _("Set the sale date of an inactive asset."))
        return cleaned


class OtherAssetValueForm(
    AddToPreviousValueMixin, MoneyInputGroupMixin, forms.ModelForm
):
    """Form for creating/editing an other asset value entry."""

    parent_field = "asset"

    class Meta:
        model = OtherAssetValue
        fields = ["value", "value_date"]
        widgets = {"value_date": DATE_WIDGET}


class EuroFundRateForm(forms.ModelForm):
    """Form for recording the yearly rate credited by a euro fund."""

    class Meta:
        model = EuroFundRate
        fields = ["year", "rate", "notes"]
        widgets = {
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 1900}),
            "rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "notes": forms.TextInput(attrs={"class": "form-control"}),
        }
