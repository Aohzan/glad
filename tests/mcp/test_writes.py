"""Tests of the write tools."""

import datetime
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from djmoney.money import Money

from budget.models import BudgetCategory, BudgetLine, BudgetYear
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
)
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
    "update_deposit",
    "delete_deposit",
    "update_account",
    "update_holding",
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


def _deposit(write_key, account, amount="250", **extra):
    return call_tool(
        write_key,
        "add_account_deposit",
        kind="saving",
        account_id=account.pk,
        amount=amount,
        date=TODAY.isoformat(),
        **extra,
    )


@pytest.mark.django_db
def test_add_account_deposit_refuses_a_duplicate(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    first = _deposit(write_key, account)
    with pytest.raises(ToolFailed, match=f"Deposit {first['id']} already"):
        _deposit(write_key, account)
    assert _deposit(write_key, account, amount="251")["id"] != first["id"]


@pytest.mark.django_db
def test_update_deposit_into_a_duplicate_is_refused(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    _deposit(write_key, account)
    other = _deposit(write_key, account, amount="251")
    with pytest.raises(ToolFailed, match="duplicate an existing entry"):
        call_tool(
            write_key,
            "update_deposit",
            kind="saving",
            deposit_id=other["id"],
            amount="250",
        )


@pytest.mark.django_db
def test_update_deposit_keeps_the_left_out_values(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    created = _deposit(write_key, account, origin="income", source="Salary")
    result = call_tool(
        write_key,
        "update_deposit",
        kind="saving",
        deposit_id=created["id"],
        amount="300",
    )
    deposit = SavingAccountDeposit.objects.get(pk=created["id"])
    assert deposit.amount.amount == 300
    assert deposit.origin == "income"
    assert deposit.source == "Salary"
    assert result["date"] == TODAY.isoformat()


@pytest.mark.django_db
def test_update_investment_deposit(write_key):
    deposit = InvestmentAccountDeposit.objects.all()[0]
    call_tool(
        write_key,
        "update_deposit",
        kind="investment",
        deposit_id=deposit.pk,
        date="2024-02-03",
        origin="transfer",
    )
    deposit.refresh_from_db()
    assert deposit.deposit_date == datetime.date(2024, 2, 3)
    assert deposit.origin == "transfer"


@pytest.mark.django_db
def test_update_deposit_reports_form_errors(write_key):
    deposit = InvestmentAccountDeposit.objects.all()[0]
    with pytest.raises(ToolFailed, match="origin"):
        call_tool(
            write_key,
            "update_deposit",
            kind="investment",
            deposit_id=deposit.pk,
            origin="lottery",
        )


@pytest.mark.django_db
def test_delete_deposit_needs_a_confirmation(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    created = _deposit(write_key, account)
    described = call_tool(
        write_key, "delete_deposit", kind="saving", deposit_id=created["id"]
    )
    assert described["deleted"] is False
    assert described["deposit"]["amount"]["amount"] == "250"
    assert SavingAccountDeposit.objects.filter(pk=created["id"]).exists()
    deleted = call_tool(
        write_key,
        "delete_deposit",
        kind="saving",
        deposit_id=created["id"],
        confirm=True,
    )
    assert deleted["deleted"] is True
    assert not SavingAccountDeposit.objects.filter(pk=created["id"]).exists()


def test_delete_deposit_is_flagged_destructive():
    tool = mcp._tool_manager.get_tool("delete_deposit")
    assert tool is not None and tool.annotations is not None
    assert tool.annotations.destructive_hint


@pytest.mark.django_db
def test_update_saving_account(write_key):
    account = SavingAccount.objects.filter(is_active=True)[0]
    owners = list(account.ownerships.values_list("user_id", "share"))
    result = call_tool(
        write_key,
        "update_account",
        kind="saving",
        account_id=account.pk,
        interest_rate="2.4",
        notes="Rate of the bank",
    )
    account.refresh_from_db()
    assert account.interest_rate == Decimal("2.4")
    assert account.commentaire == "Rate of the bank"
    assert result["interest_rate"] == "2.4"
    assert list(account.ownerships.values_list("user_id", "share")) == owners


@pytest.mark.django_db
def test_update_investment_account_and_other_asset(write_key):
    account = InvestmentAccount.objects.filter(is_active=True)[0]
    call_tool(
        write_key,
        "update_account",
        kind="investment",
        account_id=account.pk,
        institution="New bank",
    )
    account.refresh_from_db()
    assert account.institution == "New bank"
    asset = OtherAsset.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key, "update_account", kind="other", account_id=asset.pk, name="Car"
    )
    assert result["name"] == "Car"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "model", "arguments", "message"),
    [
        ("investment", InvestmentAccount, {"interest_rate": "1"}, "Only a savings"),
        ("other", OtherAsset, {"institution": "Bank"}, "only a name and notes"),
    ],
)
def test_update_account_refuses_foreign_fields(
    write_key, kind, model, arguments, message
):
    account = model.objects.filter(is_active=True)[0]
    with pytest.raises(ToolFailed, match=message):
        call_tool(
            write_key, "update_account", kind=kind, account_id=account.pk, **arguments
        )


@pytest.mark.django_db
def test_update_holding(write_key):
    holding = InvestmentAccountHolding.objects.filter(is_active=True)[0]
    result = call_tool(
        write_key,
        "update_holding",
        holding_id=holding.pk,
        isin=" fr0010315770 ",
        asset_class="equities",
        initial_value="1234.5",
    )
    holding.refresh_from_db()
    assert holding.isin == "FR0010315770"
    assert holding.asset_class == "equities"
    assert holding.initial_value.amount == Decimal("1234.5")
    assert result["asset_class"] == "equities"


@pytest.mark.django_db
def test_update_holding_validates_the_asset_class_and_the_isin(write_key):
    holding = InvestmentAccountHolding.objects.filter(is_active=True)[0]
    with pytest.raises(ToolFailed, match="asset_class"):
        call_tool(
            write_key, "update_holding", holding_id=holding.pk, asset_class="gold"
        )
    holding.auto_update_price = True
    holding.isin = "FR0010315770"
    holding.save()
    with pytest.raises(ToolFailed, match="auto_update_price"):
        call_tool(write_key, "update_holding", holding_id=holding.pk, isin="")


@pytest.mark.django_db
def test_get_data_quality_issues(api_key):
    holding = InvestmentAccountHolding.objects.filter(
        is_active=True, account__is_active=True
    )[0]
    InvestmentAccountHolding.objects.filter(pk=holding.pk).update(
        asset_class="", isin="", initial_value=Money(0, holding.account.currency)
    )
    saving = SavingAccount.objects.filter(is_active=True)[0]
    SavingAccount.objects.filter(pk=saving.pk).update(interest_rate=0)
    capped = next(
        a for a in SavingAccount.objects.filter(is_active=True) if a.ceiling_usage
    )
    SavingAccountDeposit.objects.create(
        account=capped, amount=Money(10**6, capped.currency), deposit_date=TODAY
    )
    empty = SavingAccount.objects.create(
        account_type=saving.account_type,
        name="Without deposit",
        opening_value=Money(0, "EUR"),
        opening_date=datetime.date(2024, 1, 1),
    )
    SavingAccountValue.objects.create(
        account=empty, value=Money(500, "EUR"), value_date=datetime.datetime(2025, 1, 1)
    )
    result = call_tool(api_key, "get_data_quality_issues")
    by_holding = {row["holding_id"]: row for row in result if row["kind"] == "holding"}
    assert {"no_asset_class", "no_isin", "no_purchase_value"} <= set(
        by_holding[holding.pk]["issues"]
    )
    by_account = {
        row["account"]["id"]: row for row in result if row["kind"] == "saving"
    }
    assert "no_interest_rate" in by_account[saving.pk]["issues"]
    assert "deposit_ceiling_exceeded" in by_account[capped.pk]["issues"]
    assert "no_deposits_nor_opening_value" in by_account[empty.pk]["issues"]
