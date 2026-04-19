"""Update account views for the finance app."""

import logging
from datetime import datetime

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.forms import formset_factory
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from finance.forms import (
    UpdateGlobalForm,
    UpdateInvestmentAccountHoldingAddValueForm,
    UpdateInvestmentCashAddValueForm,
    UpdateSavingAccountAddValueForm,
)
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue

_LOGGER = logging.getLogger(__name__)


def update_accounts(request):
    """Initialize formsets for saving and investment accounts."""
    UpdateSavingAccountAddValueFormSet = formset_factory(
        UpdateSavingAccountAddValueForm, extra=0
    )
    UpdateInvestmentCashAddValueFormSet = formset_factory(
        UpdateInvestmentCashAddValueForm, extra=0
    )
    UpdateInvestmentAccountHoldingAddValueFormSet = formset_factory(
        UpdateInvestmentAccountHoldingAddValueForm, extra=0
    )

    saving_accounts: QuerySet[SavingAccount] = SavingAccount.objects.filter(
        is_active=True
    )
    investment_accounts: QuerySet[InvestmentAccount] = InvestmentAccount.objects.filter(
        is_active=True
    )

    # Prepare initial data for all forms - common for both GET and POST
    saving_accounts_initial_data = []
    for account in saving_accounts:
        saving_accounts_initial_data.append(
            {
                "account_id": account.id,
                "account_name": str(account),
                "current_value": account.current_value.amount,  # For hidden field
                "current_value_display": account.current_value,  # For template display
                "new_value": account.current_value.amount,
            }
        )

    # Prepare investment accounts initial data
    investment_accounts_initial_data = {}
    for account in investment_accounts:
        investment_accounts_initial_data[str(account)] = {}

        # Cash initial data
        investment_accounts_initial_data[str(account)]["cash"] = [
            {
                "account_id": account.id,
                "account_name": str(account),
                "current_value": account.current_cash_value.amount,  # For hidden field
                "current_value_display": account.current_cash_value,  # For template display
                "new_value": account.current_cash_value.amount,
            }
        ]

        # Holdings initial data
        holding_data = []
        for holding in InvestmentAccountHolding.objects.filter(
            account=account, is_active=True
        ):
            holding_data.append(
                {
                    "holding_id": holding.id,
                    "holding_name": holding.short_name,
                    "current_value": holding.value.amount,  # For hidden field
                    "current_value_display": holding.value,  # For template display
                    "new_value": holding.value.amount,
                    "current_quantity": holding.quantity,
                    "new_quantity": holding.quantity,
                }
            )
        investment_accounts_initial_data[str(account)]["holdings"] = holding_data

    if request.method == "GET":
        global_form = UpdateGlobalForm()

        # Create formsets with initial data
        saving_accounts_formset = UpdateSavingAccountAddValueFormSet(
            initial=saving_accounts_initial_data, prefix="saving_accounts"
        )

        investment_accounts_formsets = {}
        for account in investment_accounts:
            investment_accounts_formsets[str(account)] = {}
            investment_accounts_formsets[str(account)]["cash"] = (
                UpdateInvestmentCashAddValueFormSet(
                    initial=investment_accounts_initial_data[str(account)]["cash"],
                    prefix=f"investment_{account.id}_cash",
                )
            )
            investment_accounts_formsets[str(account)]["holdings"] = (
                UpdateInvestmentAccountHoldingAddValueFormSet(
                    initial=investment_accounts_initial_data[str(account)]["holdings"],
                    prefix=f"investment_{account.id}_holdings",
                )
            )
    elif request.method == "POST":
        global_form = UpdateGlobalForm(request.POST)
        if (value := global_form.data.get("new_values_date")) is not None:
            new_values_date = parse_datetime(value)
        else:
            new_values_date = datetime.now()

        # Create formsets with both POST data and initial data
        saving_accounts_formset = UpdateSavingAccountAddValueFormSet(
            request.POST, prefix="saving_accounts", initial=saving_accounts_initial_data
        )

        investment_accounts_formsets = {}
        for account in investment_accounts:
            investment_accounts_formsets[str(account)] = {}

            investment_accounts_formsets[str(account)]["cash"] = (
                UpdateInvestmentCashAddValueFormSet(
                    request.POST,
                    prefix=f"investment_{account.id}_cash",
                    initial=investment_accounts_initial_data[str(account)]["cash"],
                )
            )

            investment_accounts_formsets[str(account)]["holdings"] = (
                UpdateInvestmentAccountHoldingAddValueFormSet(
                    request.POST,
                    prefix=f"investment_{account.id}_holdings",
                    initial=investment_accounts_initial_data[str(account)]["holdings"],
                )
            )

        # Validate global form first
        is_valid = global_form.is_valid()

        # Validate only forms where update_account is checked
        saving_accounts_formset_valid = True
        for form in saving_accounts_formset:
            if form.is_valid():
                # Only validate forms that will be processed
                if form.cleaned_data.get("update_account"):
                    # Form is valid and will be processed
                    continue
            else:
                # Check if this form should be validated (has update_account checked)
                update_account = form.data.get(f"{form.prefix}-update_account")
                if update_account:  # Only invalidate if update_account is checked
                    saving_accounts_formset_valid = False
                    break

        is_valid = is_valid and saving_accounts_formset_valid

        # Validate investment account formsets conditionally
        for account_name, formset_by_type in investment_accounts_formsets.items():
            # Validate cash formset
            cash_formset_valid = True
            for form in formset_by_type["cash"]:
                if form.is_valid():
                    continue
                else:
                    update_account = form.data.get(f"{form.prefix}-update_account")
                    if update_account:
                        cash_formset_valid = False
                        break

            # Validate holdings formset
            holdings_formset_valid = True
            for form in formset_by_type["holdings"]:
                if form.is_valid():
                    continue
                else:
                    update_account = form.data.get(f"{form.prefix}-update_account")
                    if update_account:
                        holdings_formset_valid = False
                        break

            is_valid = is_valid and cash_formset_valid and holdings_formset_valid

        if is_valid:
            updated_count = 0
            duplicate_count = 0

            # Update saving accounts
            for form in saving_accounts_formset:
                if form.cleaned_data.get("update_account") is True:
                    account = SavingAccount.objects.get(
                        id=form.cleaned_data["account_id"]
                    )
                    try:
                        with transaction.atomic():
                            SavingAccountValue.objects.create(
                                account=account,
                                value=Money(
                                    form.cleaned_data["new_value"], account.currency
                                ),
                                value_date=new_values_date,
                            )
                        updated_count += 1
                    except IntegrityError:
                        duplicate_count += 1
                        date_str = (
                            new_values_date.strftime("%Y-%m-%d")
                            if new_values_date
                            else "N/A"
                        )
                        messages.warning(
                            request,
                            _(
                                "Duplicate value ignored for account '{account}': a value of {value} already exists for the date {date}."
                            ).format(
                                account=str(account),
                                value=Money(
                                    form.cleaned_data["new_value"], account.currency
                                ),
                                date=date_str,
                            ),
                        )
            # Update investment accounts
            for account_name, formset_by_type in investment_accounts_formsets.items():
                # Process cash forms
                for form in formset_by_type["cash"]:
                    if form.cleaned_data.get("update_account") is True:
                        account = InvestmentAccount.objects.get(
                            id=form.cleaned_data["account_id"]
                        )
                        try:
                            with transaction.atomic():
                                InvestmentAccountCash.objects.create(
                                    account=account,
                                    value=Money(
                                        form.cleaned_data["new_value"], account.currency
                                    ),
                                    value_date=new_values_date,
                                )
                            updated_count += 1
                        except IntegrityError:
                            duplicate_count += 1
                            date_str = (
                                new_values_date.strftime("%Y-%m-%d")
                                if new_values_date
                                else "N/A"
                            )
                            messages.warning(
                                request,
                                _(
                                    "Duplicate cash value ignored for account '{account}': a value of {value} already exists for the date {date}."
                                ).format(
                                    account=str(account),
                                    value=Money(
                                        form.cleaned_data["new_value"], account.currency
                                    ),
                                    date=date_str,
                                ),
                            )

                # Process holdings forms
                for form in formset_by_type["holdings"]:
                    if form.cleaned_data.get("update_account") is True:
                        holding = InvestmentAccountHolding.objects.get(
                            id=form.cleaned_data["holding_id"]
                        )
                        try:
                            with transaction.atomic():
                                InvestmentAccountHoldingHistory.objects.create(
                                    holding=holding,
                                    value=Money(
                                        form.cleaned_data["new_value"],
                                        holding.account.currency,
                                    ),
                                    quantity=form.cleaned_data["new_quantity"],
                                    valuation_date=new_values_date,
                                )
                            updated_count += 1
                        except IntegrityError:
                            duplicate_count += 1
                            date_str = (
                                new_values_date.strftime("%Y-%m-%d %H:%M:%S")
                                if new_values_date
                                else "N/A"
                            )
                            messages.warning(
                                request,
                                _(
                                    "Duplicate holding value ignored for '{holding}': a value of {value} with quantity {quantity} already exists for the date {date}."
                                ).format(
                                    holding=str(holding),
                                    value=Money(
                                        form.cleaned_data["new_value"],
                                        holding.account.currency,
                                    ),
                                    quantity=form.cleaned_data["new_quantity"],
                                    date=date_str,
                                ),
                            )

            if updated_count > 0:
                messages.success(
                    request,
                    _("{count} account(s) updated successfully.").format(
                        count=updated_count
                    ),
                )
            if duplicate_count > 0 and updated_count == 0:
                messages.info(
                    request,
                    _(
                        "No updates were made. All values already exist for the selected date."
                    ),
                )
            if updated_count == 0 and duplicate_count == 0:
                messages.info(
                    request,
                    _("No changes were made."),
                )

            return redirect("finance:index")
        else:
            messages.error(request, _("Please correct the errors below."))

    return render(
        request,
        "finance/update.html",
        {
            "form": global_form,
            "saving_accounts_formset": saving_accounts_formset,
            "investment_accounts_formsets": investment_accounts_formsets,
        },
    )
