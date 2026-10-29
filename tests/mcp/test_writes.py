"""Tests of the write tools."""

import datetime
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync

from budget.models import BudgetCategory, BudgetLine, BudgetYear
from finance.models.investment_account import InvestmentAccount, InvestmentAccountCash
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from mcp_server.models import McpCallLog
from mcp_server.server import current_key, mcp
from mcp_server.tests.conftest import ToolFailed, call_tool
from property.models import Property, PropertyLedgerEntry, PropertyValue
from property.services.checks import pending_occurrences

TODAY = datetime.date.today()
WRITE_TOOLS = {
    "add_account_value",
    "add_account_deposit",
    "add_property_value",
    "add_ledger_entry",
    "check_ledger_occurrence",
    "save_budget_line",
}


def _listed(key) -> set[str]:
    token = current_key.set(key)
    try:
        return {tool.name for tool in async_to_sync(mcp.list_tools)()}
    finally:
        current_key.reset(token)


@pytest.mark.django_db
def test_write_tools_are_hidden_from_a_read_only_key(api_key, write_key):
    assert not WRITE_TOOLS & _listed(api_key)
    assert "list_budget_categories" in _listed(api_key)
    assert WRITE_TOOLS <= _listed(write_key)


@pytest.mark.django_db
def test_read_only_key_cannot_write(api_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    with pytest.raises(ToolFailed, match="read-only"):
        call_tool(
            api_key,
            "add_account_value",
            kind="saving",
            account_id=account.pk,
            value="100",
            date=TODAY.isoformat(),
        )
    assert not McpCallLog.objects.filter(api_key=api_key).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "parent_model", "model", "parent_field"),
    [
        ("saving", SavingAccount, SavingAccountValue, "account"),
        ("investment", InvestmentAccount, InvestmentAccountCash, "account"),
        ("other", OtherAsset, OtherAssetValue, "asset"),
    ],
)
def test_add_account_value(write_key, kind, parent_model, model, parent_field):
    parent = parent_model.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key,
        "add_account_value",
        kind=kind,
        account_id=parent.pk,
        value="12345.67",
        date=TODAY.isoformat(),
    )
    saved = model.objects.get(pk=result["id"])
    assert getattr(saved, parent_field) == parent
    assert saved.value.amount == Decimal("12345.67")
    assert result["value"]["currency"] == parent.currency
    log = McpCallLog.objects.get(api_key=write_key)
    assert log.is_write and log.success
    assert log.arguments["value"] == "12345.67"


@pytest.mark.django_db
def test_add_account_value_reports_form_errors(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    with pytest.raises(ToolFailed, match="value"):
        call_tool(
            write_key,
            "add_account_value",
            kind="saving",
            account_id=account.pk,
            value="1e20",
            date=TODAY.isoformat(),
        )
    assert not McpCallLog.objects.get(api_key=write_key).success


@pytest.mark.django_db
def test_add_saving_deposit_updates_the_balance(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    before = account.get_value().amount
    result = call_tool(
        write_key,
        "add_account_deposit",
        kind="saving",
        account_id=account.pk,
        amount="250",
        date=TODAY.isoformat(),
        origin="income",
    )
    deposit = SavingAccountDeposit.objects.get(pk=result["id"])
    assert deposit.origin == "income"
    assert deposit.update_account_value
    assert account.get_value().amount == before + 250


@pytest.mark.django_db
def test_add_investment_deposit_without_cash_update(write_key):
    account = InvestmentAccount.objects.filter(is_active=True)[0]
    cash_before = account.get_cash_value().amount
    call_tool(
        write_key,
        "add_account_deposit",
        kind="investment",
        account_id=account.pk,
        amount="100",
        date=TODAY.isoformat(),
        update_balance=False,
    )
    assert account.get_cash_value().amount == cash_before


@pytest.mark.django_db
def test_add_property_value(write_key):
    prop = Property.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key,
        "add_property_value",
        property_id=prop.pk,
        value="250000",
        date=TODAY.isoformat(),
    )
    value = PropertyValue.objects.get(pk=result["id"])
    assert value.property == prop
    assert value.source == PropertyValue.Source.MANUAL
    assert prop.get_value().amount == 250000


@pytest.mark.django_db
def test_add_ledger_entry(write_key):
    prop = Property.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key,
        "add_ledger_entry",
        property_id=prop.pk,
        flow_type="expense",
        management_category="maintenance",
        amount="180.50",
        entry_date=TODAY.isoformat(),
        description="Plumber",
        third_party="Dupont",
    )
    entry = PropertyLedgerEntry.objects.get(pk=result["id"])
    assert entry.property == prop
    assert entry.amount.amount == Decimal("180.50")
    assert result["label"] == "Dupont - Plumber"


@pytest.mark.django_db
def test_add_recurring_recoverable_ledger_entry(write_key):
    prop = Property.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key,
        "add_ledger_entry",
        property_id=prop.pk,
        flow_type="expense",
        management_category="coownership",
        amount="300",
        entry_date=TODAY.isoformat(),
        recurrence_type="quarterly",
        recurrence_end_date=(TODAY + datetime.timedelta(days=365)).isoformat(),
        reference_period=TODAY.replace(day=1).isoformat(),
        is_recoverable=True,
    )
    entry = PropertyLedgerEntry.objects.get(pk=result["id"])
    assert entry.is_recoverable
    assert entry.recurrence_type == "quarterly"
    assert entry.recurrence_end_date is not None


@pytest.mark.django_db
def test_add_ledger_entry_runs_the_model_validation(write_key):
    prop = Property.objects.filter(is_active=True)[0]
    with pytest.raises(ToolFailed, match="management_category|flow"):
        call_tool(
            write_key,
            "add_ledger_entry",
            property_id=prop.pk,
            flow_type="expense",
            management_category="rent_collected",
            amount="100",
            entry_date=TODAY.isoformat(),
        )
    assert not PropertyLedgerEntry.objects.filter(property=prop, amount=100).exists()


@pytest.mark.django_db
def test_add_ledger_entry_refuses_the_lease_of_another_property(write_key):
    first, second = Property.objects.filter(
        is_active=True, leases__isnull=False
    ).distinct()[:2]
    with pytest.raises(ToolFailed, match="lease"):
        call_tool(
            write_key,
            "add_ledger_entry",
            property_id=first.pk,
            flow_type="income",
            management_category="rent_collected",
            amount="700",
            entry_date=TODAY.isoformat(),
            lease_id=second.leases.all()[0].pk,
        )


def test_ledger_tool_lists_the_categories():
    tool = mcp._tool_manager.get_tool("add_ledger_entry")
    assert tool is not None
    assert "rent_collected" in tool.description
    assert "{categories}" not in tool.description


@pytest.mark.django_db
def test_check_ledger_occurrence(write_key):
    pending = pending_occurrences(up_to=TODAY)[0]
    result = call_tool(
        write_key,
        "check_ledger_occurrence",
        entry_id=pending.entry.pk,
        occurrence_date=pending.planned_date.isoformat(),
        actual_amount="10",
    )
    assert result["checked"]
    assert result["amount"]["amount"] == "10"
    remaining = {(p.entry.pk, p.planned_date) for p in pending_occurrences(up_to=TODAY)}
    assert (pending.entry.pk, pending.planned_date) not in remaining


@pytest.mark.django_db
def test_check_ledger_occurrence_refuses_an_unknown_date(write_key):
    pending = pending_occurrences(up_to=TODAY)[0]
    with pytest.raises(ToolFailed, match="not a scheduled occurrence"):
        call_tool(
            write_key,
            "check_ledger_occurrence",
            entry_id=pending.entry.pk,
            occurrence_date=(
                pending.planned_date + datetime.timedelta(days=1)
            ).isoformat(),
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"actual_date": (TODAY + datetime.timedelta(days=3)).isoformat()}, "future"),
        ({"actual_amount": "0"}, "positive"),
    ],
)
def test_check_ledger_occurrence_validates_the_actual_values(
    write_key, arguments, message
):
    pending = pending_occurrences(up_to=TODAY)[0]
    with pytest.raises(ToolFailed, match=message):
        call_tool(
            write_key,
            "check_ledger_occurrence",
            entry_id=pending.entry.pk,
            occurrence_date=pending.planned_date.isoformat(),
            **arguments,
        )


@pytest.mark.django_db
def test_list_budget_categories(api_key):
    result = call_tool(api_key, "list_budget_categories")
    assert len(result) == BudgetCategory.objects.count()
    assert {"id", "name", "kind", "parent_id"} == result[0].keys()


@pytest.mark.django_db
def test_save_budget_line_adds_then_edits(write_key, user):
    year = BudgetYear.objects.all()[0].year
    category = BudgetCategory.objects.filter(kind="expense")[0]
    created = call_tool(
        write_key,
        "save_budget_line",
        year=year,
        category_id=category.pk,
        label="Gym",
        amount="420",
        person_id=user.pk,
    )
    line = BudgetLine.objects.get(pk=created["id"])
    assert line.person == user
    assert line.amount.amount == 420
    call_tool(
        write_key,
        "save_budget_line",
        year=year,
        category_id=category.pk,
        label="Gym",
        amount="480",
        line_id=line.pk,
    )
    line.refresh_from_db()
    assert line.amount.amount == 480
    assert line.person is None


@pytest.mark.django_db
def test_save_budget_line_unknown_year(write_key):
    with pytest.raises(ToolFailed, match="No budget for 1900"):
        call_tool(
            write_key,
            "save_budget_line",
            year=1900,
            category_id=1,
            label="x",
            amount="1",
        )


@pytest.mark.django_db
def test_save_budget_line_refuses_a_negative_amount(write_key):
    year = BudgetYear.objects.all()[0].year
    category = BudgetCategory.objects.all()[0]
    with pytest.raises(ToolFailed, match="amount"):
        call_tool(
            write_key,
            "save_budget_line",
            year=year,
            category_id=category.pk,
            label="x",
            amount="-5",
        )
