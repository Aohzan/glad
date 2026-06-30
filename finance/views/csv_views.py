"""CSV import/export views for the finance app."""

import csv
import datetime
import io
import logging
from typing import cast

import dateparser
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.forms import ChoiceField, formset_factory
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from finance.forms import CSVAccountMappingForm, CSVExportForm, CSVImportForm
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue

_LOGGER = logging.getLogger(__name__)


def csv_export(request):
    """View for exporting data to CSV."""
    if request.method == "POST":
        form = CSVExportForm(request.POST)
        if form.is_valid():
            csv_type = form.cleaned_data["csv_type"]
            selected = form.cleaned_data.get("accounts", [])
            from finance.models.investment_account import InvestmentAccount
            from finance.models.saving_account import SavingAccount

            accounts: list[InvestmentAccount | SavingAccount] = []
            if selected:
                for value in selected:
                    if value.startswith("investment-"):
                        pk = value.split("-", 1)[1]
                        try:
                            account = InvestmentAccount.objects.get(pk=pk)
                            accounts.append(account)
                        except InvestmentAccount.DoesNotExist, ValueError:
                            _LOGGER.warning(
                                f"Account {pk} not found or invalid for user {request.user}"
                            )
                            messages.warning(
                                request, _("Some accounts could not be found.")
                            )
                    elif value.startswith("saving-"):
                        pk = value.split("-", 1)[1]
                        try:
                            account = SavingAccount.objects.get(pk=pk)
                            accounts.append(account)
                        except SavingAccount.DoesNotExist, ValueError:
                            _LOGGER.warning(
                                f"Account {pk} not found or invalid for user {request.user}"
                            )
                            messages.warning(
                                request, _("Some accounts could not be found.")
                            )
            if not accounts:
                messages.error(request, _("No account selected or found for export."))
                return render(request, "finance/csv_export.html", {"form": form})
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = (
                f'attachment; filename="{csv_type}_export.csv"'
            )
            writer = csv.writer(response)
            exported = False
            if csv_type == "saving_value":
                writer.writerow(["account", "value", "date"])
                for account in accounts:
                    if isinstance(account, SavingAccount):
                        for value in SavingAccountValue.objects.filter(
                            account=account
                        ).order_by("-value_date"):
                            writer.writerow(
                                [
                                    str(account),
                                    str(value.value),
                                    value.value_date.strftime("%Y-%m-%d %H:%M:%S"),
                                ]
                            )
                            exported = True
            elif csv_type == "investment_cash":
                writer.writerow(["account", "value", "date"])
                for account in accounts:
                    if isinstance(account, InvestmentAccount):
                        for cash in InvestmentAccountCash.objects.filter(
                            account=account
                        ).order_by("-value_date"):
                            writer.writerow(
                                [
                                    str(account),
                                    str(cash.value),
                                    cash.value_date.strftime("%Y-%m-%d %H:%M:%S"),
                                ]
                            )
                            exported = True
            elif csv_type == "investment_holding":
                writer.writerow(
                    [
                        "account",
                        "holding",
                        "value",
                        "quantity",
                        "date",
                    ]
                )
                for account in accounts:
                    if isinstance(account, InvestmentAccount):
                        for holding in InvestmentAccountHolding.objects.filter(
                            account=account, is_active=True
                        ):
                            for (
                                history
                            ) in InvestmentAccountHoldingHistory.objects.filter(
                                holding=holding
                            ).order_by("-valuation_date"):
                                writer.writerow(
                                    [
                                        str(account),
                                        holding.short_name,
                                        str(history.value),
                                        history.quantity,
                                        history.valuation_date.strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        ),
                                    ]
                                )
                                exported = True
            if not exported:
                messages.error(
                    request,
                    _("No data to export for selected accounts."),
                )
                return render(request, "finance/csv_export.html", {"form": form})
            return response
    else:
        form = CSVExportForm()
    return render(request, "finance/csv_export.html", {"form": form})


def csv_import(request):
    """View for importing data from CSV."""
    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_type = form.cleaned_data["csv_type"]
            csv_file = request.FILES["csv_file"]

            # Read the CSV file
            csv_data = csv_file.read().decode("utf-8")
            csv_reader = csv.reader(io.StringIO(csv_data))

            # Get the header row
            header = next(csv_reader)

            # Convert to list to be able to iterate multiple times
            csv_data_list = list(csv_reader)

            # Store the CSV data in the session
            request.session["csv_data"] = csv_data_list
            request.session["csv_header"] = header
            request.session["csv_type"] = csv_type

            # Build and check according to csv_type
            unique_account_names = []
            app_account_choices = []
            if csv_type in ("saving_value", "investment_cash"):
                # Accept both new and old header formats for backward compatibility
                required_headers = ["account", "value", "date"]
                legacy_headers = ["account_name", "value", "value_date"]

                # Check if we have the required headers or legacy headers
                has_required = all(h in header for h in required_headers)
                has_legacy = all(h in header for h in legacy_headers)

                if not (has_required or has_legacy):
                    messages.error(
                        request,
                        _(
                            "CSV file is missing required columns for the selected type."
                        ),
                    )
                    return render(request, "finance/csv_import.html", {"form": form})

                if csv_type == "saving_value":
                    app_account_choices = [
                        (a.id, str(a))
                        for a in SavingAccount.objects.filter(is_active=True)
                    ]
                else:
                    app_account_choices = [
                        (a.id, str(a))
                        for a in InvestmentAccount.objects.filter(is_active=True)
                    ]

                # Use appropriate header names
                account_header = "account" if has_required else "account_name"
                unique_account_names = set(
                    row[header.index(account_header)] for row in csv_data_list
                )

            elif csv_type == "investment_holding":
                if (
                    "account" not in header
                    or "holding" not in header
                    or "value" not in header
                    or "quantity" not in header
                    or "date" not in header
                ):
                    messages.error(
                        request,
                        _(
                            "CSV file is missing required columns for the selected type."
                        ),
                    )
                    return render(request, "finance/csv_import.html", {"form": form})
                unique_account_names = set(
                    row[header.index("account")] + " - " + row[header.index("holding")]
                    for row in csv_data_list
                )
                app_account_choices = [
                    (h.id, str(h))
                    for h in InvestmentAccountHolding.objects.filter(is_active=True)
                ]

            # Store app_account_choices in session for reuse in confirmation
            request.session["app_account_choices"] = app_account_choices

            # Extract unique account names and try to match them with app accounts
            initial_account_data = []
            for csv_name in sorted(unique_account_names):
                # Try to find a matching app account
                matched_app_account = None
                for app_id, app_name in app_account_choices:
                    # Try exact match first
                    if csv_name.lower() == app_name.lower():
                        matched_app_account = app_id
                        break
                    # Try partial match (csv name contained in app name or vice versa)
                    elif (csv_name.lower() in app_name.lower()) or (
                        app_name.lower() in csv_name.lower()
                    ):
                        matched_app_account = app_id
                        break
                    elif csv_type == "investment_holding":
                        # For holdings, check if the csv_name matches "account - holding"
                        if " - " in csv_name:
                            account_name, holding_name = csv_name.split(" - ", 1)
                            if (
                                account_name.lower() in app_name.lower()
                                and holding_name.lower() in app_name.lower()
                            ):
                                matched_app_account = app_id
                                break

                initial_account_data.append(
                    {
                        "csv_account_name": csv_name,
                        "app_account_id": matched_app_account,
                    }
                )

            AccountMappingFormSet = formset_factory(CSVAccountMappingForm, extra=0)
            account_formset = AccountMappingFormSet(
                initial=initial_account_data, prefix="accounts"
            )
            # Set choices for each form
            for form in account_formset:
                field = cast(ChoiceField, form.fields["app_account_id"])
                field.choices = [("", "--- Choose the account ---")] + (
                    app_account_choices
                )

            # Create a context dictionary
            context = {
                "account_formset": account_formset,
                "formset": account_formset,  # For backward compatibility with tests
                "csv_type": csv_type,
                "header": header,
                "preview_rows": csv_data_list[:5],  # Show first 5 rows for preview
            }

            return render(request, "finance/csv_mapping.html", context)
    else:
        form = CSVImportForm()

    return render(request, "finance/csv_import.html", {"form": form})


def csv_import_confirm(request):
    """View for confirming CSV import after column mapping."""
    if request.method == "POST":
        csv_type = request.session.get("csv_type")
        csv_data = request.session.get("csv_data")
        csv_header = request.session.get("csv_header")
        app_account_choices = request.session.get("app_account_choices", [])

        if not all([csv_type, csv_data, csv_header]):
            messages.error(request, _("CSV import session expired. Please try again."))
            return redirect("finance:csv_import")

        # Create a formset for account mapping
        AccountMappingFormSet = formset_factory(CSVAccountMappingForm, extra=0)
        account_formset = AccountMappingFormSet(request.POST, prefix="accounts")

        # Set choices for each form in the formset
        for form in account_formset:
            field = cast(ChoiceField, form.fields["app_account_id"])
            field.choices = [("", "--- Choose the account ---")] + (app_account_choices)

        if not account_formset.is_valid():
            messages.error(request, _("Please correct the errors below."))
            return render(
                request,
                "finance/csv_mapping.html",
                {
                    "account_formset": account_formset,
                    "csv_type": csv_type,
                    "header": csv_header,
                    "preview_rows": csv_data[:5],  # Show first 5 rows for preview
                },
            )

        imported_count = 0
        ignored_count = 0
        error_rows = []

        # Build account mapping dictionary
        account_mapping = {}
        for form in account_formset:
            csv_account_name = form.cleaned_data.get("csv_account_name")
            app_account_id = form.cleaned_data.get("app_account_id")
            if csv_account_name and app_account_id:
                account_mapping[csv_account_name] = app_account_id

        try:
            for row_index, data in enumerate(csv_data):
                try:
                    if csv_type in ["saving_value", "investment_cash"]:
                        account_col = "account"
                        value_col = "value"
                        date_col = "date"

                        # Get the account name from the CSV row
                        csv_account_name = data[csv_header.index(account_col)]
                        app_account_id = account_mapping.get(csv_account_name)
                        # get value
                        new_value = data[csv_header.index(value_col)]
                        new_value = "".join(
                            c
                            for c in data[csv_header.index(value_col)]
                            if c.isdigit() or c in [".", ","]
                        )
                        new_value = new_value.replace(",", ".")
                        # get date
                        new_date = dateparser.parse(data[csv_header.index(date_col)])

                        if not app_account_id:
                            error_rows.append(
                                (row_index, _("No mapping found for account"))
                            )
                            continue

                        if csv_type == "saving_value":
                            currency = SavingAccount.objects.get(
                                id=app_account_id
                            ).currency
                            try:
                                with transaction.atomic():
                                    SavingAccountValue.objects.create(
                                        account_id=app_account_id,
                                        value=Money(
                                            new_value,
                                            currency,
                                        ),
                                        value_date=new_date,
                                    )
                                imported_count += 1
                            except IntegrityError:
                                # Record already exists, ignore it
                                ignored_count += 1
                                _LOGGER.debug(
                                    "Duplicate saving account value ignored: account=%s, date=%s, value=%s",
                                    app_account_id,
                                    new_date,
                                    new_value,
                                )
                        elif csv_type == "investment_cash":
                            currency = InvestmentAccount.objects.get(
                                id=app_account_id
                            ).currency
                            try:
                                with transaction.atomic():
                                    InvestmentAccountCash.objects.create(
                                        account_id=app_account_id,
                                        value=Money(
                                            new_value,
                                            currency,
                                        ),
                                        value_date=new_date,
                                    )
                                imported_count += 1
                            except IntegrityError:
                                # Record already exists, ignore it
                                ignored_count += 1
                                _LOGGER.debug(
                                    "Duplicate investment cash value ignored: account=%s, date=%s, value=%s",
                                    app_account_id,
                                    new_date,
                                    new_value,
                                )

                    elif csv_type == "investment_holding":
                        # For holdings, the mapping key is "account - holding"
                        csv_account_name = data[csv_header.index("account")]
                        holding_name = data[csv_header.index("holding")]
                        mapping_key = f"{csv_account_name} - {holding_name}"
                        holding_id = account_mapping.get(mapping_key)

                        # get value
                        new_value = data[csv_header.index("value")]
                        new_value = "".join(
                            c
                            for c in data[csv_header.index("value")]
                            if c.isdigit() or c in [".", ","]
                        )
                        new_value = new_value.replace(",", ".")
                        new_date = dateparser.parse(data[csv_header.index("date")])

                        # get quantity
                        quantity_str = data[csv_header.index("quantity")]
                        if quantity_str:
                            # Clean quantity string similar to value
                            clean_quantity = "".join(
                                c
                                for c in quantity_str
                                if c.isdigit() or c in [".", ","]
                            )
                            clean_quantity = clean_quantity.replace(",", ".")
                            new_quantity = (
                                float(clean_quantity) if clean_quantity else None
                            )
                        else:
                            new_quantity = None

                        if not holding_id:
                            error_rows.append(
                                (row_index, _("No mapping found for holding"))
                            )
                            continue

                        holding = InvestmentAccountHolding.objects.get(id=holding_id)
                        try:
                            with transaction.atomic():
                                InvestmentAccountHoldingHistory.objects.create(
                                    holding=holding,
                                    value=Money(
                                        new_value,
                                        holding.account.currency,
                                    ),
                                    quantity=new_quantity,
                                    valuation_date=new_date,
                                )
                            imported_count += 1
                        except IntegrityError:
                            # Record already exists, ignore it
                            ignored_count += 1
                            _LOGGER.debug(
                                "Duplicate holding history ignored: holding=%s, date=%s, value=%s, quantity=%s",
                                holding_id,
                                new_date,
                                new_value,
                                new_quantity,
                            )

                except (
                    ValueError,
                    KeyError,
                    SavingAccount.DoesNotExist,
                    InvestmentAccount.DoesNotExist,
                    InvestmentAccountHolding.DoesNotExist,
                ) as e:
                    error_rows.append((row_index, str(e)))

        except Exception as e:
            messages.error(request, _("An error occurred during import: ") + str(e))
            return redirect("finance:csv_import")

        # Clear session data
        request.session.pop("csv_data", None)
        request.session.pop("csv_header", None)
        request.session.pop("csv_type", None)
        request.session.pop("app_account_choices", None)

        # Show results to user
        if imported_count > 0:
            if ignored_count > 0:
                messages.success(
                    request,
                    _(
                        "Successfully imported {} records. {} duplicate records were ignored."
                    ).format(imported_count, ignored_count),
                )
            else:
                messages.success(
                    request,
                    _("Successfully imported {} records.").format(imported_count),
                )
        elif ignored_count > 0:
            messages.info(
                request,
                _("No new records imported. {} duplicate records were ignored.").format(
                    ignored_count
                ),
            )

        if error_rows:
            error_message = _("Errors in rows: ") + ", ".join(
                [f"{row + 1}: {error}" for row, error in error_rows[:5]]
            )
            if len(error_rows) > 5:
                error_message += _(" and {} more errors").format(len(error_rows) - 5)
            messages.warning(request, error_message)

    return redirect("finance:csv_import")


def csv_export_synthesis(request):
    """Export a synthesis CSV of all active saving and investment accounts."""
    now = datetime.datetime.now()
    today = now.date()
    date_str = today.strftime("%d/%m/%Y")
    header = [
        _("Type"),
        _("Owner"),
        _("Institution"),
        _("Value at %(date)s") % {"date": date_str},
    ]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="synthesis_export.csv"'
    writer = csv.writer(response)
    writer.writerow(header)

    total = 0

    for account in SavingAccount.objects.filter(is_active=True).order_by(
        "account_type", "name", "owner", "institution"
    ):
        value = account.get_value(max_date=now)
        total += value.amount
        writer.writerow(
            [
                str(account.account_type),
                account.owner or "",
                account.institution or "",
                str(value.amount),
            ]
        )

    for account in InvestmentAccount.objects.filter(is_active=True).order_by(
        "account_type", "name", "owner", "institution"
    ):
        value = account.get_value(max_date=now)
        total += value.amount
        writer.writerow(
            [
                str(account.account_type),
                account.owner or "",
                account.institution or "",
                str(value.amount),
            ]
        )

    writer.writerow(
        [
            _("Total"),
            "",
            "",
            str(total),
        ]
    )

    return response
