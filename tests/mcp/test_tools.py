"""Tests of the read tools on the fixture data."""

import datetime
from decimal import Decimal

import pytest
from djmoney.money import Money

from budget.models import BudgetYear
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountType,
    SavingAccountValue,
)
from mcp_server.models import McpCallLog
from mcp_server.tests.conftest import ToolFailed, call_tool
from property.models import Lease, Property


@pytest.mark.django_db
def test_get_net_worth(api_key):
    result = call_tool(api_key, "get_net_worth")
    assert result["currency"] == "EUR"
    assert {"net", "gross", "debt", "debt_ratio_pct"} <= result["summary"].keys()
    classes = result["asset_classes"]
    assert classes[0]["assets"][0]["value"]
    assert len({c["total"] for c in classes}) == len(classes)
    assert sum(Decimal(c["total"]) for c in classes) == Decimal(
        result["summary"]["net"]
    )
    assert sum(Decimal(c["share_pct"]) for c in classes) == pytest.approx(100, abs=0.1)
    assert result["by_person"]
    assert result["left_out_other_currencies"] == []


def _usd_account() -> SavingAccount:
    account = SavingAccount.objects.create(
        account_type=SavingAccountType.objects.all()[0],
        name="Brokerage USD",
        opening_value=Money(1000, "USD"),
        opening_date=datetime.date(2024, 1, 1),
    )
    SavingAccountValue.objects.create(
        account=account,
        value=Money(1500, "USD"),
        value_date=datetime.datetime(2025, 1, 1),
    )
    return account


@pytest.mark.django_db
def test_get_net_worth_lists_the_assets_in_another_currency(api_key):
    _usd_account()
    result = call_tool(api_key, "get_net_worth")
    names = [a["name"] for c in result["asset_classes"] for a in c["assets"]]
    assert not any("Brokerage USD" in name for name in names)
    (left_out,) = result["left_out_other_currencies"]
    assert "Brokerage USD" in left_out["name"]
    assert left_out["value"] == {"amount": "1500", "currency": "USD"}


@pytest.mark.django_db
def test_get_net_worth_history(api_key):
    result = call_tool(api_key, "get_net_worth_history", months=3)
    assert len(result["points"]) == 4
    assert result["points"][-1]["date"] == datetime.date.today().isoformat()


@pytest.mark.django_db
def test_get_allocation(api_key):
    result = call_tool(api_key, "get_allocation")
    assert result["by_asset_class"]
    assert result["by_liquidity"]
    assert all(row["key"] for row in result["by_asset_class"])
    assert all(
        isinstance(row["share_pct"], str)
        and len(row["share_pct"].partition(".")[2]) <= 2
        for row in result["by_asset_class"]
    )
    assert Decimal(result["negative_total"]) <= 0


@pytest.mark.django_db
def test_get_allocation_names_the_unclassified_assets(api_key):
    from finance.models.investment_account import InvestmentAccountHolding

    InvestmentAccountHolding.objects.filter(is_active=True).update(asset_class="")
    result = call_tool(api_key, "get_allocation")
    assert "unclassified" in {row["key"] for row in result["by_asset_class"]}


@pytest.mark.django_db
def test_get_upcoming_deadlines(api_key):
    result = call_tool(api_key, "get_upcoming_deadlines", limit=5)
    assert len(result) <= 5
    assert {"date", "days_left", "kind", "title"} <= result[0].keys()


@pytest.mark.django_db
def test_get_pending_checks(api_key):
    result = call_tool(api_key, "get_pending_checks")
    entries = result["unchecked_entries"]
    assert entries
    assert entries[0]["count"] >= 1
    assert entries[0]["oldest_date"] <= entries[0]["latest_date"]
    assert result["leases"][0]["issues"] or result["leases"][0]["arrears"] != "0"


@pytest.mark.django_db
def test_list_accounts(api_key):
    result = call_tool(api_key, "list_accounts")
    assert {row["kind"] for row in result} == {"saving", "investment", "other"}
    assert all(row["is_active"] for row in result)
    assert all(row["holder"] for row in result)
    accounts = [row for row in result if row["kind"] != "other"]
    assert any(row["xirr_pct"] for row in accounts)
    assert all(
        row["last_value_date"] is None or len(row["last_value_date"]) == 10
        for row in result
    )
    assert any("deposit_ceiling" in row for row in accounts)
    with_closed = call_tool(api_key, "list_accounts", include_closed=True)
    assert len(with_closed) >= len(result)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "model", "keys"),
    [
        (
            "saving",
            SavingAccount,
            {"interest_rate", "values", "deposits", "xirr_pct", "holder"},
        ),
        (
            "investment",
            InvestmentAccount,
            {"cash", "holdings", "deposits", "xirr_pct", "last_value_date"},
        ),
        ("other", OtherAsset, {"acquisition_value", "values"}),
    ],
)
def test_get_account(api_key, kind, model, keys):
    account = model.objects.filter(is_active=True)[0]
    result = call_tool(
        api_key, "get_account", kind=kind, account_id=account.pk, history=2
    )
    assert result["id"] == account.pk
    assert keys <= result.keys()
    assert len(result["values" if "values" in keys else "deposits"]) <= 2
    dates = [
        row["date"] for row in result.get("values", []) + result.get("deposits", [])
    ]
    assert all(len(date) == 10 for date in dates)


@pytest.mark.django_db
def test_xirr_unavailable_reason(api_key):
    account = _usd_account()
    account.opening_value = Money(0, "USD")
    account.save()
    result = call_tool(api_key, "get_account", kind="saving", account_id=account.pk)
    assert result["xirr_pct"] is None
    assert result["xirr_unavailable_reason"] == "no_deposits_nor_opening_value"


@pytest.mark.django_db
def test_get_account_unknown(api_key):
    with pytest.raises(ToolFailed, match="Not found"):
        call_tool(api_key, "get_account", kind="saving", account_id=999999)
    log = McpCallLog.objects.get(api_key=api_key)
    assert not log.success
    assert log.error == "Not found."


@pytest.mark.django_db
def test_list_properties(api_key):
    result = call_tool(api_key, "list_properties")
    assert result
    assert all(row["is_active"] for row in result)
    assert len(call_tool(api_key, "list_properties", include_sold=True)) >= len(result)


@pytest.mark.django_db
def test_get_property(api_key):
    prop = Property.objects.filter(is_active=True, loans__isnull=False)[0]
    result = call_tool(api_key, "get_property", property_id=prop.pk)
    assert result["name"] == prop.name
    assert result["loans"][0]["remaining_balance"]
    assert set(result["monthly_flows"]) == {"rents", "charges", "loan", "cashflow"}
    assert "income" in result["ledger_this_year"]


@pytest.mark.django_db
def test_get_property_ledger(api_key):
    prop = Property.objects.filter(is_active=True, ledger_entries__isnull=False)[0]
    today = datetime.date.today()
    result = call_tool(
        api_key,
        "get_property_ledger",
        property_id=prop.pk,
        date_from=f"{today.year - 1}-01-01",
        date_to=today.isoformat(),
    )
    assert result["occurrences"]
    dates = [o["date"] for o in result["occurrences"]]
    assert dates == sorted(dates)
    assert result["income_by_category"] or result["expenses_by_category"]


@pytest.mark.django_db
def test_get_property_ledger_truncates(api_key, monkeypatch):
    monkeypatch.setattr("mcp_server.tools.property.MAX_OCCURRENCES", 1)
    prop = Property.objects.filter(is_active=True, ledger_entries__isnull=False)[0]
    today = datetime.date.today()
    result = call_tool(
        api_key,
        "get_property_ledger",
        property_id=prop.pk,
        date_from=f"{today.year - 1}-01-01",
        date_to=today.isoformat(),
    )
    assert len(result["occurrences"]) == 1
    assert result["truncated"]


@pytest.mark.django_db
def test_get_property_ledger_refuses_reversed_dates(api_key):
    prop = Property.objects.all()[0]
    with pytest.raises(ToolFailed, match="before"):
        call_tool(
            api_key,
            "get_property_ledger",
            property_id=prop.pk,
            date_from="2025-12-31",
            date_to="2025-01-01",
        )


@pytest.mark.django_db
def test_get_lmnp_summary(api_key):
    prop = Property.objects.filter(tax_regime=Property.TaxRegime.LMNP_REEL)[0]
    year = datetime.date.today().year - 1
    result = call_tool(api_key, "get_lmnp_summary", property_id=prop.pk, year=year)
    assert result["year"] == year
    assert result["summary"]
    assert "overall_status" in result["checklist"]


@pytest.mark.django_db
def test_get_lmnp_summary_refuses_another_regime(api_key):
    prop = Property.objects.exclude(tax_regime=Property.TaxRegime.LMNP_REEL)[0]
    with pytest.raises(ToolFailed, match="LMNP"):
        call_tool(api_key, "get_lmnp_summary", property_id=prop.pk, year=2025)


@pytest.mark.django_db
def test_list_leases(api_key):
    result = call_tool(api_key, "list_leases")
    assert result
    assert {"arrears", "issues", "managed_by_agency"} <= result[0].keys()


@pytest.mark.django_db
def test_get_lease(api_key):
    lease = Lease.objects.filter(status=Lease.Status.ACTIVE)[0]
    result = call_tool(api_key, "get_lease", lease_id=lease.pk)
    assert result["id"] == lease.pk
    assert result["periods"]
    assert result["tenants"]


@pytest.mark.django_db
def test_get_budget(api_key):
    year = BudgetYear.objects.all()[0].year
    result = call_tool(api_key, "get_budget", year=year)
    assert result["year"] == year
    assert result["expenses"]
    assert "income" in result["indicators"]

    def nodes(rows):
        for row in rows:
            yield row
            yield from nodes(row.get("children", []))

    assert any("line_id" in row for row in nodes(result["expenses"]))


@pytest.mark.django_db
def test_get_budget_unknown_year(api_key):
    with pytest.raises(ToolFailed, match="No budget for 1900"):
        call_tool(api_key, "get_budget", year=1900)


@pytest.mark.django_db
def test_call_without_key():
    with pytest.raises(ToolFailed, match="Not authenticated"):
        call_tool(None, "list_accounts")


@pytest.mark.django_db
def test_unexpected_error_is_hidden_and_logged(api_key, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr("mcp_server.tools.overview.upcoming_deadlines", boom)
    with pytest.raises(ToolFailed, match="Internal error") as exc_info:
        call_tool(api_key, "get_upcoming_deadlines")
    assert "secret detail" not in str(exc_info.value)
    log = McpCallLog.objects.get(api_key=api_key)
    assert "secret detail" in log.error
