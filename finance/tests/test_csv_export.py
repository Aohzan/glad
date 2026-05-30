"""Tests for CSV export and confirm edge paths."""

import csv
import datetime
import io
from types import SimpleNamespace

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
from finance.tests.helpers import csv_confirm_post_data, setup_csv_import_session


@pytest.mark.django_db
def test_csv_export_view_get(user_client):
    response = user_client.get(reverse("finance:csv_export"))
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_csv_export_no_accounts_selected(user_client):
    response = user_client.post(
        reverse("finance:csv_export"), {"csv_type": "saving_value"}
    )
    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_csv_export_no_data_path_with_mismatched_type(
    user_client, active_saving_account
):
    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "investment_cash",
            "accounts": [f"saving-{active_saving_account.id}"],
        },
    )
    assert response.status_code == 200
    messages = list(response.context["messages"])
    assert any("no data to export" in str(message).lower() for message in messages)


@pytest.mark.django_db
def test_csv_export_saving_value_no_data_due_related_name_path(
    user_client, active_saving_account
):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1250, "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )

    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "saving_value",
            "accounts": [f"saving-{active_saving_account.id}"],
        },
    )

    assert response.status_code == 200
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="saving_value_export.csv"'
    )
    assert b"account" in response.content


@pytest.mark.django_db
def test_csv_export_investment_cash_no_data_due_related_name_path(
    user_client, active_investment_account
):
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(2300, "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )

    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "investment_cash",
            "accounts": [f"investment-{active_investment_account.id}"],
        },
    )

    assert response.status_code == 200
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="investment_cash_export.csv"'
    )
    assert b"account" in response.content


@pytest.mark.django_db
def test_csv_export_investment_holding_success(user_client, active_investment_account):
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="NASDAQ ETF",
        code="QQQ",
        is_active=True,
        initial_value=Money(100, "EUR"),
        initial_quantity=1,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(120, "EUR"),
        quantity=1.1,
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )

    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "investment_holding",
            "accounts": [f"investment-{active_investment_account.id}"],
        },
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    content = response.content.decode("utf-8")
    assert "account,holding,value,quantity,date" in content
    assert "NASDAQ ETF" in content


@pytest.mark.django_db
def test_csv_export_no_data_for_selected_account(user_client, active_saving_account):
    response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "saving_value",
            "accounts": [f"saving-{active_saving_account.id}"],
        },
    )
    assert response.status_code == 200
    messages = list(response.context["messages"])
    assert any("no data to export" in str(message).lower() for message in messages)


@pytest.mark.django_db
def test_csv_import_confirm_session_expired(user_client):
    response = user_client.post(reverse("finance:csv_import_confirm"), {})
    assert response.status_code == 302
    assert response.url == reverse("finance:csv_import")


@pytest.mark.django_db
def test_csv_import_confirm_invalid_formset_shows_mapping_again(
    user_client, active_saving_account
):
    setup_csv_import_session(user_client, active_saving_account)

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        csv_confirm_post_data(active_saving_account.name, ""),
    )

    assert response.status_code == 200
    assert "account_formset" in response.context


@pytest.mark.django_db
def test_csv_import_confirm_generic_error_redirects(
    user_client, active_saving_account, monkeypatch
):
    setup_csv_import_session(user_client, active_saving_account)

    monkeypatch.setattr(
        "finance.views.csv_views.dateparser.parse",
        lambda value: (_ for _ in ()).throw(RuntimeError("parse error")),
    )

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        csv_confirm_post_data(active_saving_account.name, active_saving_account.id),
    )

    assert response.status_code == 302
    assert response.url == reverse("finance:csv_import")


@pytest.mark.django_db
def test_csv_import_confirm_adds_warning_for_unmapped_account(
    user_client, active_saving_account
):
    unmapped_data = [
        [f"Unmapped {c}", "123", "2024-01-01 12:00:00"]
        for c in ("A", "B", "C", "D", "E", "F")
    ]
    setup_csv_import_session(user_client, active_saving_account, csv_data=unmapped_data)

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        csv_confirm_post_data("Mapped Name", active_saving_account.id),
    )

    assert response.status_code == 302
    assert response.url == reverse("finance:csv_import")


@pytest.mark.django_db
def test_csv_import_legacy_headers_supported(user_client):
    csv_data = io.StringIO()
    writer = csv.writer(csv_data)
    writer.writerow(["account_name", "value", "value_date"])
    writer.writerow(["Some Account", "100", "2024-01-01 10:00:00"])
    csv_data.seek(0)

    upload = SimpleUploadedFile(
        "legacy.csv", csv_data.getvalue().encode(), content_type="text/csv"
    )

    response = user_client.post(
        reverse("finance:csv_import"),
        {"csv_type": "saving_value", "csv_file": upload},
    )

    assert response.status_code == 200
    assert "formset" in response.context


@pytest.mark.django_db
def test_csv_export_saving_and_cash_manager_paths(
    user_client,
    active_saving_account,
    active_investment_account,
    monkeypatch,
):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1111, "EUR"),
        value_date=datetime.datetime.now(),
    )
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(2222, "EUR"),
        value_date=datetime.datetime.now(),
    )

    saving_proxy = active_saving_account
    saving_proxy.savingaccountvalue_set = SimpleNamespace(
        all=lambda: SimpleNamespace(order_by=lambda order: saving_proxy.values.all())
    )

    cash_proxy = active_investment_account
    cash_proxy.investmentaccountcash_set = SimpleNamespace(
        all=lambda: SimpleNamespace(order_by=lambda order: cash_proxy.cash_values.all())
    )

    monkeypatch.setattr(
        "finance.views.csv_views.SavingAccount.objects.get", lambda pk: saving_proxy
    )
    monkeypatch.setattr(
        "finance.views.csv_views.InvestmentAccount.objects.get", lambda pk: cash_proxy
    )

    saving_response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "saving_value",
            "accounts": [f"saving-{active_saving_account.id}"],
        },
    )
    cash_response = user_client.post(
        reverse("finance:csv_export"),
        {
            "csv_type": "investment_cash",
            "accounts": [f"investment-{active_investment_account.id}"],
        },
    )

    assert saving_response["Content-Type"] == "text/csv"
    assert cash_response["Content-Type"] == "text/csv"


@pytest.mark.django_db
def test_csv_import_confirm_all_duplicates_info_message(
    user_client, active_saving_account
):
    duplicate_date = datetime.datetime(2024, 1, 1, 10, 0, 0)
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1000, "EUR"),
        value_date=duplicate_date,
    )

    setup_csv_import_session(user_client, active_saving_account)

    response = user_client.post(
        reverse("finance:csv_import_confirm"),
        csv_confirm_post_data(active_saving_account.name, active_saving_account.id),
    )

    assert response.status_code == 302
    assert response.url == reverse("finance:csv_import")
