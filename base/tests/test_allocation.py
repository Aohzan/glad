"""Tests for the allocation breakdown and the emergency fund."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from base.choices import AssetClass, Liquidity
from base.services.allocation import (
    Allocation,
    AllocationItem,
    compute_allocation,
    emergency_fund,
)
from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentAccountType,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount, SavingAccountType
from property.models import Property, PropertyLoan
from property.models.scpi import SCPI, SCPIInvestment, SCPISharePrice

CURRENCY = "XAU"  # isolates the test data from any other fixture


def _item(amount, asset_class=AssetClass.CASH, liquidity=Liquidity.IMMEDIATE):
    return AllocationItem("x", Decimal(amount), asset_class, liquidity)


class TestAllocation:
    def test_rows_and_percent(self):
        allocation = Allocation(
            "EUR",
            [
                _item(300),
                _item(100, AssetClass.EQUITIES, Liquidity.CONDITIONAL),
                _item(-50, AssetClass.EQUITIES),
                _item(600, ""),
            ],
        )
        assert allocation.total == Decimal(1000)
        rows = allocation.by_asset_class()
        assert [(r.key, r.percent) for r in rows] == [
            ("", 60.0),
            ("cash", 30.0),
            ("equities", 10.0),
        ]
        assert rows[0].label == "Not classified"
        liquidity = allocation.by_liquidity()
        assert liquidity[0].label == "Available immediately"
        assert allocation.amount_for_liquidity(Liquidity.IMMEDIATE) == Decimal(900)

    def test_empty(self):
        allocation = Allocation("EUR")
        assert allocation.by_asset_class() == []
        assert allocation.total == 0
        assert allocation.negative_total == 0

    def test_negative_total(self):
        allocation = Allocation("EUR", [_item(300), _item(-50), _item(-20)])
        assert allocation.total == Decimal(300)
        assert allocation.negative_total == Decimal(-70)


class TestEmergencyFund:
    def _fund(self, available, expenses):
        allocation = Allocation("EUR", [_item(available)])
        return emergency_fund(allocation, expenses and Decimal(expenses))

    def test_levels(self):
        assert self._fund(2000, 1000).level == "danger"
        assert self._fund(4000, 1000).level == "success"
        assert self._fund(9000, 1000).level == "info"
        assert self._fund(4000, 1000).months == 4.0
        assert self._fund(4000, 1000).target_range == (Decimal(3000), Decimal(6000))

    def test_without_expenses(self):
        fund = self._fund(4000, None)
        assert fund.months is None
        assert fund.level is None
        assert fund.target_range is None


@pytest.fixture
def assets(db):
    money = lambda amount: Money(Decimal(amount), CURRENCY)
    livret = SavingAccountType.objects.get_or_create(code="LA", name="Livret A")[0]
    SavingAccount.objects.create(
        account_type=livret, name="Alloc livret", opening_value=money(10000)
    )
    pea = InvestmentAccountType.objects.get_or_create(code="PEA", name="PEA")[0]
    account = InvestmentAccount.objects.create(
        account_type=pea, name="Alloc PEA", opening_cash_value=money(500)
    )
    InvestmentAccountHolding.objects.create(
        account=account,
        name="World ETF",
        asset_class=AssetClass.EQUITIES,
        initial_quantity=Decimal(10),
        initial_value=money(5000),
    )
    InvestmentAccountHolding.objects.create(
        account=account, name="Unknown", initial_value=money(1000)
    )
    Property.objects.create(
        name="Alloc flat",
        property_type=Property.APARTMENT,
        buying_value=money(100000),
        buying_date=datetime.date(2020, 1, 1),
    )
    scpi = SCPI.objects.create(name="Alloc SCPI")
    SCPISharePrice.objects.create(
        scpi=scpi,
        date=datetime.date(2020, 1, 1),
        subscription_value=money(200),
    )
    SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=datetime.date(2020, 1, 1),
        shares_count=Decimal(10),
        unit_purchase_price=money(200),
    )
    OtherAsset.objects.create(
        name="Alloc BTC",
        category=OtherAsset.Category.CRYPTO,
        acquisition_value=money(2000),
        acquisition_date=datetime.date(2020, 1, 1),
    )


@pytest.mark.django_db
class TestComputeAllocation:
    def test_every_source(self, assets):
        allocation = compute_allocation(CURRENCY)
        by_class = {r.key: r.amount for r in allocation.by_asset_class()}
        assert by_class[AssetClass.CASH] == Decimal(10500)
        assert by_class[AssetClass.EQUITIES] == Decimal(5000)
        assert by_class[""] == Decimal(1000)
        assert by_class[AssetClass.REAL_ESTATE] == Decimal(102000)
        assert by_class[AssetClass.CRYPTO] == Decimal(2000)
        by_liquidity = {r.key: r.amount for r in allocation.by_liquidity()}
        assert by_liquidity[Liquidity.IMMEDIATE] == Decimal(12000)
        assert by_liquidity[Liquidity.CONDITIONAL] == Decimal(6500)
        assert by_liquidity[Liquidity.ILLIQUID] == Decimal(102000)

    def test_underwater_property_left_out(self, assets):
        """A pie chart cannot show the negative equity of a property."""
        prop = Property.objects.get(name="Alloc flat")
        PropertyLoan.objects.create(
            property=prop,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2045, 1, 1),
            original_amount=Money(500000, CURRENCY),
            interest_rate=Decimal("2.0"),
        )
        allocation = compute_allocation(CURRENCY)
        by_class = {r.key: r.amount for r in allocation.by_asset_class()}
        # Only the SCPI is left in real estate.
        assert by_class[AssetClass.REAL_ESTATE] == Decimal(2000)
        assert allocation.negative_total < 0
        assert allocation.negative_total == sum(
            i.amount for i in allocation.items if i.label == str(prop)
        )

    def test_other_currency_is_ignored(self, assets):
        assert compute_allocation("JPY").items == []


@pytest.mark.django_db
class TestAllocationView:
    def test_page(self, user_client):
        response = user_client.get(reverse("allocation"))
        assert response.status_code == 200
        assert 'id="emergency-fund"' in response.content.decode()
        assert response.context["fund"].monthly_expenses is None

    def test_page_shows_the_negative_total(self, user_client, monkeypatch):
        allocation = Allocation("EUR", [_item(1000), _item(-250)])
        monkeypatch.setattr(
            "base.views.compute_allocation", lambda *_args, **_kwargs: allocation
        )
        content = user_client.get(reverse("allocation")).content.decode()
        assert 'id="allocation-negative"' in content
        assert "assets worth less than nothing, -€250.00" in content

    def test_page_without_negative_total(self, user_client, monkeypatch):
        allocation = Allocation("EUR", [_item(1000)])
        monkeypatch.setattr(
            "base.views.compute_allocation", lambda *_args, **_kwargs: allocation
        )
        content = user_client.get(reverse("allocation")).content.decode()
        assert 'id="allocation-negative"' not in content

    def test_save_expenses(self, user_client, user):
        response = user_client.post(reverse("allocation"), {"monthly_expenses": "2500"})
        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.monthly_expenses == Decimal(2500)
        response = user_client.get(reverse("allocation"))
        assert response.context["fund"].monthly_expenses == Decimal(2500)
        assert "Months of expenses covered" in response.content.decode()

    def test_expenses_from_the_budget(self, user_client):
        category = BudgetCategory.objects.create(name="Rent", kind=BudgetKind.EXPENSE)
        budget_year = BudgetYear.objects.create(
            year=datetime.date.today().year,
            include_properties=False,
            include_finance=False,
        )
        BudgetLine.objects.create(
            budget_year=budget_year,
            category=category,
            label="Rent",
            amount=Money(12000, "EUR"),
        )
        response = user_client.get(reverse("allocation"))
        assert response.context["fund"].monthly_expenses == Decimal(1000)
        assert response.context["budget_year"] == budget_year
        assert (
            reverse("budget:year", args=[budget_year.year]) in response.content.decode()
        )

    def test_invalid_expenses(self, user_client):
        response = user_client.post(reverse("allocation"), {"monthly_expenses": "-1"})
        assert response.status_code == 200
