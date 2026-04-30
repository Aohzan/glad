"""Extended tests for CSV export and import views to increase coverage."""

import csv
import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccountValue

# ---------------------------------------------------------------------------
# csv_export — form validation failures
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_export_form_invalid_no_accounts_field(user_client):
    """POST without accounts field yields form error (no messages)."""
    response = user_client.post(
        reverse("finance:csv_export"),
        {"csv_type": "investment_cash"},
    )
    assert response.status_code == 200
    # Form should have errors, no messages framework messages
    assert response.context["form"].errors


@pytest.mark.django_db
def test_csv_export_get_renders_form(user_client):
    """GET request renders the export form with no messages."""
    response = user_client.get(reverse("finance:csv_export"))
    assert response.status_code == 200
    assert "form" in response.context
    assert not response.context["form"].errors


# ---------------------------------------------------------------------------
# csv_export — investment_holding no data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_export_investment_holding_no_data(user_client, active_investment_account):
    """Export investment_holding with account that has no active holdings reports no data."""
    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "investment_holding",
            "accounts": [f"investment-{active_investment_account.id}"],
        },
    )
    assert response.status_code == 200
    msg_texts = [str(m) for m in response.context["messages"]]
    assert any("no data" in t.lower() for t in msg_texts)


# ---------------------------------------------------------------------------
# csv_import — invalid headers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_invalid_headers_saving_value(user_client):
    """CSV with wrong headers for saving_value shows error message."""
    csv_data = io.StringIO()
    writer = csv.writer(csv_data)
    writer.writerow(["wrong_col", "another_col"])
    writer.writerow(["Something", "100"])
    csv_data.seek(0)

    upload = SimpleUploadedFile(
        "bad.csv", csv_data.getvalue().encode(), content_type="text/csv"
    )

    response = user_client.post(
        reverse("finance:csv_import"),
        {"csv_type": "saving_value", "csv_file": upload},
    )

    assert response.status_code == 200
    msg_texts = [str(m) for m in response.context["messages"]]
    assert any("missing" in t.lower() or "required" in t.lower() for t in msg_texts)


@pytest.mark.django_db
def test_csv_import_invalid_headers_investment_cash(user_client):
    """CSV with wrong headers for investment_cash shows error message."""
    csv_data = io.StringIO()
    writer = csv.writer(csv_data)
    writer.writerow(["x", "y", "z"])
    writer.writerow(["Account", "1000", "2025-01-01"])
    csv_data.seek(0)

    upload = SimpleUploadedFile(
        "bad_cash.csv", csv_data.getvalue().encode(), content_type="text/csv"
    )

    response = user_client.post(
        reverse("finance:csv_import"),
        {"csv_type": "investment_cash", "csv_file": upload},
    )

    assert response.status_code == 200
    msg_texts = [str(m) for m in response.context["messages"]]
    assert any("missing" in t.lower() or "required" in t.lower() for t in msg_texts)


@pytest.mark.django_db
def test_csv_import_invalid_headers_investment_holding(user_client):
    """CSV with missing columns for investment_holding shows error message."""
    csv_data = io.StringIO()
    writer = csv.writer(csv_data)
    writer.writerow(["account", "value"])  # missing: holding, quantity, date
    writer.writerow(["Account", "1000"])
    csv_data.seek(0)

    upload = SimpleUploadedFile(
        "bad_holding.csv", csv_data.getvalue().encode(), content_type="text/csv"
    )

    response = user_client.post(
        reverse("finance:csv_import"),
        {"csv_type": "investment_holding", "csv_file": upload},
    )

    assert response.status_code == 200
    msg_texts = [str(m) for m in response.context["messages"]]
    assert any("missing" in t.lower() or "required" in t.lower() for t in msg_texts)


# ---------------------------------------------------------------------------
# csv_import — legacy header for investment_cash
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_legacy_headers_investment_cash(user_client):
    """Legacy headers (account_name, value_date) are accepted for investment_cash."""
    csv_data = io.StringIO()
    writer = csv.writer(csv_data)
    writer.writerow(["account_name", "value", "value_date"])
    writer.writerow(["Some Investment Account", "3000", "2024-06-01 10:00:00"])
    csv_data.seek(0)

    upload = SimpleUploadedFile(
        "legacy_cash.csv", csv_data.getvalue().encode(), content_type="text/csv"
    )

    response = user_client.post(
        reverse("finance:csv_import"),
        {"csv_type": "investment_cash", "csv_file": upload},
    )

    assert response.status_code == 200
    assert "formset" in response.context


# ---------------------------------------------------------------------------
# csv_import_confirm — more than 5 error rows gets truncated message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_confirm_more_than_5_error_rows(user_client, active_saving_account):
    """When more than 5 rows have errors the message includes 'and N more errors'."""
    session = user_client.session
    session["csv_type"] = "saving_value"
    session["csv_header"] = ["account", "value", "date"]
    # 7 rows with unmapped accounts
    session["csv_data"] = [
        [f"Unknown Account {i}", "100", "2024-01-01 12:00:00"] for i in range(7)
    ]
    session["app_account_choices"] = [
        (active_saving_account.id, str(active_saving_account))
    ]
    session.save()

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        {
            "accounts-TOTAL_FORMS": "1",
            "accounts-INITIAL_FORMS": "1",
            "accounts-MIN_NUM_FORMS": "0",
            "accounts-MAX_NUM_FORMS": "1000",
            "accounts-0-csv_account_name": "Mapped",
            "accounts-0-app_account_id": str(active_saving_account.id),
        },
    )

    assert response.status_code == 302
    # Check that the "and N more errors" message was added (via messages framework)
    # We can only inspect messages after a redirect by following it
    response2 = user_client.get(reverse("finance:csv_import"))
    msg_texts = [str(m) for m in response2.context["messages"]]
    assert any("more error" in t.lower() for t in msg_texts)


# ---------------------------------------------------------------------------
# csv_import_confirm — import + ignored mix produces success message with count
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_confirm_mixed_imported_and_duplicates(
    user_client, active_saving_account
):
    """When some rows are new and some are duplicates, success message includes both counts."""
    # Pre-create a duplicate value
    duplicate_date = datetime.datetime(2024, 3, 15, 10, 0, 0)
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1000, "EUR"),
        value_date=duplicate_date,
    )

    session = user_client.session
    session["csv_type"] = "saving_value"
    session["csv_header"] = ["account", "value", "date"]
    session["csv_data"] = [
        # duplicate
        [active_saving_account.name, "1000", "2024-03-15 10:00:00"],
        # new
        [active_saving_account.name, "1200", "2024-04-01 12:00:00"],
    ]
    session["app_account_choices"] = [
        (active_saving_account.id, str(active_saving_account))
    ]
    session.save()

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        {
            "accounts-TOTAL_FORMS": "1",
            "accounts-INITIAL_FORMS": "1",
            "accounts-MIN_NUM_FORMS": "0",
            "accounts-MAX_NUM_FORMS": "1000",
            "accounts-0-csv_account_name": active_saving_account.name,
            "accounts-0-app_account_id": str(active_saving_account.id),
        },
    )

    assert response.status_code == 302
    response2 = user_client.get(reverse("finance:csv_import"))
    msg_texts = [str(m) for m in response2.context["messages"]]
    assert any("imported" in t.lower() or "duplicate" in t.lower() for t in msg_texts)


# ---------------------------------------------------------------------------
# csv_import_confirm — investment_cash import success
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_confirm_investment_cash_success(
    user_client, active_investment_account
):
    """Confirm step successfully creates InvestmentAccountCash entries."""
    session = user_client.session
    session["csv_type"] = "investment_cash"
    session["csv_header"] = ["account", "value", "date"]
    session["csv_data"] = [
        [active_investment_account.name, "4500.00", "2024-05-01 10:00:00"]
    ]
    session["app_account_choices"] = [
        (active_investment_account.id, str(active_investment_account))
    ]
    session.save()

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        {
            "accounts-TOTAL_FORMS": "1",
            "accounts-INITIAL_FORMS": "1",
            "accounts-MIN_NUM_FORMS": "0",
            "accounts-MAX_NUM_FORMS": "1000",
            "accounts-0-csv_account_name": active_investment_account.name,
            "accounts-0-app_account_id": str(active_investment_account.id),
        },
    )

    assert response.status_code == 302
    assert InvestmentAccountCash.objects.filter(
        account=active_investment_account
    ).exists()


# ---------------------------------------------------------------------------
# csv_import_confirm — investment_holding import success
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_csv_import_confirm_investment_holding_success(
    user_client, active_investment_account
):
    """Confirm step successfully creates InvestmentAccountHoldingHistory entries."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="World ETF",
        code="WRLD",
        is_active=True,
        initial_value=Money(100, "EUR"),
        initial_quantity=Decimal("5"),
    )
    mapping_key = f"{active_investment_account.name} - World ETF (WRLD)"

    session = user_client.session
    session["csv_type"] = "investment_holding"
    session["csv_header"] = ["account", "holding", "value", "quantity", "date"]
    session["csv_data"] = [
        [
            active_investment_account.name,
            "World ETF (WRLD)",
            "600.00",
            "5",
            "2024-06-01 10:00:00",
        ]
    ]
    session["app_account_choices"] = [(holding.id, str(holding))]
    session.save()

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        {
            "accounts-TOTAL_FORMS": "1",
            "accounts-INITIAL_FORMS": "1",
            "accounts-MIN_NUM_FORMS": "0",
            "accounts-MAX_NUM_FORMS": "1000",
            "accounts-0-csv_account_name": mapping_key,
            "accounts-0-app_account_id": str(holding.id),
        },
    )

    assert response.status_code == 302
    assert InvestmentAccountHoldingHistory.objects.filter(holding=holding).exists()


# ---------------------------------------------------------------------------
# Needed imports for Decimal
# ---------------------------------------------------------------------------
from decimal import Decimal  # noqa: E402
