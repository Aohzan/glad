"""Tests of the budget summary, its indicators, the sankey data, the comparison and the copy."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from base.models import EconomicIndex, EconomicIndexValue
from budget.models import BudgetKind, BudgetYear
from budget.services.comparison import (
    compare,
    comparison_chart,
    inflation_between,
    last_12_months_inflation,
    previous_year,
    with_previous,
    year_inflation,
)
from budget.services.copy import copy_year
from budget.services.perspective import Perspective
from budget.services.sankey import sankey_payload
from budget.services.summary import (
    ACCOUNT_DEPOSITS,
    ACCOUNT_WITHDRAWALS,
    BudgetNode,
    budget_monthly_expenses,
    build_budget,
)
from budget.tests.conftest import YEAR, add_line, day
from finance.models.base import DepositOrigin
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
)
from property.models import Property, PropertyLedgerEntry, PropertyLoan
from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment


def _keys(nodes):
    return [n.key for n in nodes]


@pytest.fixture
def lines(categories, budget_year, admin_user, user):
    """A salary for each adult, shared energy, a car loan and employee savings."""
    add_line(budget_year, categories["salaries"], 30000, "Salary A", admin_user)
    add_line(budget_year, categories["salaries"], 20000, "Salary B", user)
    add_line(budget_year, categories["energy"], 2400, "Power")
    add_line(budget_year, categories["car"], 3600, "Car")
    add_line(budget_year, categories["savings"], 1200, "PEE", admin_user)
    return budget_year


@pytest.mark.django_db
class TestBudgetNode:
    def test_totals_and_changes(self):
        child = BudgetNode(
            key="a",
            label="A",
            kind=BudgetKind.EXPENSE,
            source="line",
            amount=Decimal(120),
        )
        node = BudgetNode(
            key="g",
            label="G",
            kind=BudgetKind.EXPENSE,
            source="category",
            children=[child],
        )
        assert node.total == 120
        assert node.monthly == 10
        assert node.delta is None
        assert node.delta_percent is None
        assert node.delta_tone == ""
        node.previous = Decimal(100)
        assert node.delta == 20
        assert node.delta_percent == 20
        assert node.delta_tone == "g-neg"
        income = BudgetNode(
            key="i",
            label="I",
            kind=BudgetKind.INCOME,
            source="line",
            amount=Decimal(90),
        )
        income.previous = Decimal(100)
        assert income.delta_tone == "g-neg"
        income.amount = Decimal(110)
        assert income.delta_tone == "g-pos"
        assert list(node.walk()) == [node, child]

    def test_prune_keeps_empty_lines(self):
        empty = BudgetNode(
            key="e", label="E", kind=BudgetKind.EXPENSE, source="category"
        )
        node = BudgetNode(
            key="g",
            label="G",
            kind=BudgetKind.EXPENSE,
            source="category",
            children=[empty],
        )
        node.prune()
        assert node.children == []


@pytest.mark.django_db
class TestBuildBudget:
    def test_household(self, categories, lines, household):
        summary = build_budget(lines, household)
        assert _keys(summary.resources) == [f"category:{categories['salaries'].pk}"]
        assert summary.resources_total == Decimal(50000)
        assert summary.expenses_total == Decimal(6000)
        assert summary.savings_total == Decimal(1200)
        housing = summary.expenses[0]
        assert housing.label == "Housing"
        assert housing.children[0].label == "Energy"
        assert housing.children[0].children[0].person == "Household"
        indicators = summary.indicators
        assert indicators.income == Decimal(50000)
        assert indicators.monthly_income == Decimal(50000) / 12
        assert indicators.monthly_expenses == Decimal(500)
        assert indicators.capacity == Decimal(44000)
        assert indicators.savings_rate == Decimal(88)
        assert indicators.enrichment_rate == Decimal(88)
        assert indicators.debt_payments == Decimal(3600)
        assert indicators.debt_ratio == Decimal("7.2")
        assert not indicators.debt_ratio_exceeded
        assert indicators.monthly_left_to_live == (Decimal(50000) - 3600) / 12
        assert indicators.balance == Decimal(42800)
        assert summary.balance is not None
        assert summary.balance.key == "balance:remaining"
        assert summary.balance.kind == BudgetKind.SAVING
        assert len(list(summary.nodes())) == 12

    def test_person(self, lines, admin_user, user):
        members = frozenset({admin_user.pk, user.pk})
        summary = build_budget(
            lines, Perspective(person_id=admin_user.pk, members=members, adults=2)
        )
        indicators = summary.indicators
        assert indicators.income == Decimal(30000)
        assert indicators.expenses == Decimal(3000)
        assert indicators.savings == Decimal(1200)
        salary = summary.resources[0].children
        assert [n.label for n in salary] == ["Salary A"]
        assert salary[0].person == admin_user.username

    def test_deficit_and_empty_budget(self, categories, budget_year, household):
        add_line(budget_year, categories["salaries"], 1000)
        add_line(budget_year, categories["energy"], 1500)
        summary = build_budget(budget_year, household)
        assert summary.indicators.balance == Decimal(-500)
        assert summary.balance is not None
        assert summary.balance.key == "balance:deficit"
        assert summary.balance.total == Decimal(500)
        empty = BudgetYear.objects.create(
            year=YEAR + 5, include_properties=False, include_finance=False
        )
        nothing = build_budget(empty, household)
        assert nothing.balance is None
        assert nothing.indicators.savings_rate is None
        assert nothing.indicators.enrichment_rate is None
        assert nothing.indicators.debt_ratio is None

    def test_other_currency_lines_are_left_out(
        self, categories, budget_year, household
    ):
        add_line(budget_year, categories["salaries"], 1000)
        line = add_line(budget_year, categories["salaries"], 5000, "Dollars")
        line.amount = Money(5000, "USD")
        line.save()
        assert (
            build_budget(budget_year, household, currency="EUR").indicators.income
            == 1000
        )

    def test_automatic_flows(self, categories, household):
        budget_year = BudgetYear.objects.create(year=YEAR)
        add_line(budget_year, categories["salaries"], 40000)
        rental = Property.objects.create(
            name="Rental",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2000, 1, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=rental,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            amount=Money(10000, "EUR"),
            entry_date=day(6),
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            description="Rents",
        )
        PropertyLedgerEntry.objects.create(
            property=rental,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            amount=Money(1000, "EUR"),
            entry_date=day(10),
            management_category=PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
            description="Tax",
        )
        PropertyLoan.objects.create(
            property=rental,
            name="Mortgage",
            start_date=datetime.date(2000, 1, 1),
            end_date=datetime.date(2020, 1, 1),
            original_amount=Money(120000, "EUR"),
            interest_rate=Decimal("2.0"),
        )
        kind = SavingAccountType.objects.create(name="Booklet", code="BKT")
        account = SavingAccount.objects.create(
            account_type=kind,
            name="Booklet",
            opening_date=datetime.date(2000, 1, 1),
            opening_value=Money(0, "EUR"),
        )
        SavingAccountDeposit.objects.create(
            account=account,
            amount=Money(2000, "EUR"),
            deposit_date=datetime.datetime(YEAR, 3, 1),
        )
        other = SavingAccount.objects.create(
            account_type=kind,
            name="Other",
            opening_date=datetime.date(2000, 1, 1),
            opening_value=Money(0, "EUR"),
        )
        SavingAccountDeposit.objects.create(
            account=other,
            amount=Money(-500, "EUR"),
            deposit_date=datetime.datetime(YEAR, 3, 1),
        )

        summary = build_budget(budget_year, household)
        keys = {n.key for n in summary.nodes()}
        assert f"auto:property:{rental.pk}:income:rent_collected" in keys
        assert f"auto:property:{rental.pk}:loan:principal" in keys
        assert f"account:saving:{account.pk}" in keys
        assert f"account:saving:{other.pk}" in keys
        loan = rental.loans.get().schedule().paid_between(day(1), day(12, 31))
        indicators = summary.indicators
        assert indicators.income == Decimal(50000)
        assert indicators.withdrawals == Decimal(500)
        assert indicators.principal == loan.principal
        assert indicators.debt_payments == loan.total
        assert indicators.debt_income == Decimal(40000) + Decimal(7000)
        assert indicators.expenses == Decimal(1000) + loan.total
        assert indicators.savings == Decimal(2000)
        assert indicators.enrichment_rate is not None
        assert indicators.savings_rate is not None
        assert indicators.enrichment_rate > indicators.savings_rate

        fund = SCPI.objects.create(name="Fund")
        SCPIInvestment.objects.create(
            scpi=fund,
            subscription_date=day(2),
            shares_count=Decimal(4),
            unit_purchase_price=Money(Decimal(250), "EUR"),
        )
        SCPIDividend.objects.create(
            scpi=fund, payment_date=day(9), net_amount=Money(60, "EUR")
        )
        with_scpi = build_budget(budget_year, household)
        assert with_scpi.indicators.income == Decimal(50060)
        assert with_scpi.indicators.debt_income == Decimal(47000) + Decimal(42)
        assert with_scpi.indicators.savings == Decimal(3000)
        assert f"auto:scpi:{fund.pk}:subscriptions" in {
            n.key for n in with_scpi.nodes()
        }

        budget_year.excluded_properties.add(rental)
        budget_year.include_finance = False
        budget_year.save()
        lean = build_budget(budget_year, household)
        assert lean.indicators.income == Decimal(40060)
        assert lean.indicators.savings == Decimal(1000)

        budget_year.include_properties = False
        budget_year.include_finance = True
        budget_year.save()
        accounts_only = build_budget(budget_year, household)
        assert accounts_only.indicators.income == Decimal(40000)
        assert accounts_only.indicators.savings == Decimal(2000)


@pytest.mark.django_db
class TestAccountOrigins:
    def test_exceptional_deposit_and_guessed_origins(self, categories, household):
        budget_year = BudgetYear.objects.create(year=YEAR, include_properties=False)
        add_line(budget_year, categories["salaries"], 10000)
        kind = SavingAccountType.objects.create(name="Booklet", code="BKT")
        booklet, other = (
            SavingAccount.objects.create(
                account_type=kind,
                name=name,
                opening_date=datetime.date(2000, 1, 1),
                opening_value=Money(0, "EUR"),
            )
            for name in ("Booklet", "Other")
        )

        def deposit(account, amount, month, origin=DepositOrigin.UNKNOWN):
            SavingAccountDeposit.objects.create(
                account=account,
                amount=Money(amount, "EUR"),
                deposit_date=datetime.datetime(YEAR, month, 1),
                origin=origin,
            )

        deposit(booklet, 20000, 2, DepositOrigin.EXCEPTIONAL)
        deposit(booklet, -3000, 4)
        deposit(other, 3000, 4)
        deposit(other, 1000, 6)
        summary = build_budget(budget_year, household)
        indicators = summary.indicators
        assert indicators.income == Decimal(10000)
        assert indicators.exceptional == Decimal(20000)
        assert indicators.savings == Decimal(21000)
        assert indicators.balance == Decimal(9000)
        assert indicators.savings_rate == Decimal(100)
        keys = {n.key for n in summary.nodes()}
        assert f"account:saving:{booklet.pk}:exceptional" in keys
        assert summary.guessed_transfers == 2
        assert summary.guessed_income == 1


def _savings_account(name):
    kind, _created = SavingAccountType.objects.get_or_create(name="Booklet", code="BKT")
    return SavingAccount.objects.create(
        account_type=kind,
        name=name,
        opening_date=datetime.date(2000, 1, 1),
        opening_value=Money(0, "EUR"),
    )


def _move(account, amount, month, origin=DepositOrigin.INCOME):
    SavingAccountDeposit.objects.create(
        account=account,
        amount=Money(amount, "EUR"),
        deposit_date=datetime.datetime(YEAR, month, 1),
        origin=origin,
    )


@pytest.mark.django_db
class TestNetAccountFlows:
    @pytest.fixture
    def finance_year(self, categories):
        budget_year = BudgetYear.objects.create(year=YEAR, include_properties=False)
        add_line(budget_year, categories["salaries"], 10000)
        return budget_year

    def test_one_net_flow_per_account(self, finance_year, household):
        boost = _savings_account("Boost")
        _move(boost, 75000, 2, DepositOrigin.EXCEPTIONAL)
        _move(boost, -40000, 11)
        summary = build_budget(finance_year, household)
        keys = {n.key: n.total for n in summary.nodes()}
        assert keys[ACCOUNT_DEPOSITS] == Decimal(35000)
        assert ACCOUNT_WITHDRAWALS not in keys
        assert keys["auto:accounts:exceptional"] == Decimal(75000)
        assert summary.indicators.balance == Decimal(50000)

    def test_sankey_deducts_the_withdrawals_from_the_deposits(
        self, finance_year, household
    ):
        _move(_savings_account("Old"), -4000, 3)
        _move(_savings_account("A"), 6000, 4)
        _move(_savings_account("B"), 2000, 4)
        payload = sankey_payload(build_budget(finance_year, household))
        assert ACCOUNT_WITHDRAWALS not in [n["id"] for n in payload["left"]]
        deposits = next(n for n in payload["right"] if n["id"] == ACCOUNT_DEPOSITS)
        assert deposits["label"] == "Net account deposits"
        assert deposits["value"] == 4000
        assert [c["value"] for c in deposits["children"]] == [3000, 1000]
        assert payload["total"] == sum(n["value"] for n in payload["right"])

    def test_sankey_keeps_the_net_withdrawals(self, finance_year, household):
        _move(_savings_account("Old"), -5000, 3)
        _move(_savings_account("A"), 1000, 4)
        payload = sankey_payload(build_budget(finance_year, household))
        assert ACCOUNT_DEPOSITS not in [n["id"] for n in payload["right"]]
        withdrawals = next(n for n in payload["left"] if n["id"] == ACCOUNT_WITHDRAWALS)
        assert withdrawals["label"] == "Net withdrawals from savings"
        assert withdrawals["value"] == 4000


@pytest.mark.django_db
class TestSankey:
    def test_payload(self, lines, household):
        payload = sankey_payload(build_budget(lines, household))
        assert payload["currency"] == "EUR"
        assert payload["total"] == 50000
        assert [n["label"] for n in payload["left"]] == ["Salaries"]
        right = [n["label"] for n in payload["right"]]
        assert right == ["Housing", "Loans", "Employee savings", "Not allocated"]
        housing = payload["right"][0]
        assert housing["value"] == 2400
        assert housing["children"][0]["children"][0]["source"] == "line"

    def test_balanced_budget(self, categories, budget_year, household):
        add_line(budget_year, categories["salaries"], 1000)
        add_line(budget_year, categories["energy"], 1000)
        summary = build_budget(budget_year, household)
        assert summary.balance is None
        assert len(list(summary.nodes())) == 5
        payload = sankey_payload(summary)
        assert [n["label"] for n in payload["right"]] == ["Housing"]

    def test_deficit_on_the_left(self, categories, budget_year, household):
        add_line(budget_year, categories["salaries"], 1000)
        add_line(budget_year, categories["energy"], 1500)
        payload = sankey_payload(build_budget(budget_year, household))
        assert [n["label"] for n in payload["left"]] == ["Salaries", "Deficit"]


def _cpi(period: datetime.date, value: str):
    EconomicIndexValue.objects.create(
        index=EconomicIndex.CPI, period=period, value=Decimal(value)
    )


@pytest.mark.django_db
class TestComparison:
    @pytest.fixture(autouse=True)
    def no_cpi(self):
        """Drop the CPI values the session fixtures may hold."""
        EconomicIndexValue.objects.filter(index=EconomicIndex.CPI).delete()

    def test_inflation(self):
        assert last_12_months_inflation() is None
        _cpi(datetime.date(YEAR - 1, 12, 1), "100")
        _cpi(datetime.date(YEAR, 12, 1), "102.5")
        assert year_inflation(YEAR) == Decimal("2.5")
        assert (
            inflation_between(datetime.date(1990, 1, 1), datetime.date(YEAR, 12, 1))
            is None
        )
        assert last_12_months_inflation() == Decimal("2.5")

    def test_last_12_months_without_old_value(self):
        _cpi(datetime.date(YEAR, 12, 1), "102.5")
        assert last_12_months_inflation() is None

    def test_with_previous(self, categories, lines, household):
        assert with_previous(build_budget(lines, household)) == (None, None)
        previous = BudgetYear.objects.create(
            year=YEAR - 1, include_properties=False, include_finance=False
        )
        add_line(previous, categories["energy"], 2000, "Power")
        add_line(
            previous,
            categories["salaries"],
            30000,
            "Salary A",
            lines.lines.get(label="Salary A").person,
        )
        assert previous_year(lines) == previous
        summary = build_budget(lines, household)
        indicators, inflation = with_previous(summary)
        assert indicators is not None
        assert indicators.income == Decimal(30000)
        assert inflation is None
        assert summary.has_previous
        energy = summary.expenses[0].children[0]
        assert energy.previous == Decimal(2000)
        assert energy.delta_percent == Decimal(20)
        salary_b = next(n for n in summary.nodes() if n.label == "Salary B")
        assert salary_b.previous == 0
        chart = comparison_chart(summary)
        assert chart["labels"] == ["Housing", "Loans", "Employee savings"]
        assert chart["previous"] == [2000.0, 0.0, 0.0]
        assert chart["current"] == [2400.0, 3600.0, 1200.0]

    def test_compare_sums_duplicate_keys(self, categories, budget_year, household):
        add_line(budget_year, categories["energy"], 100, "Power")
        add_line(budget_year, categories["energy"], 50, "Power")
        before = build_budget(budget_year, household)
        after = build_budget(budget_year, household)
        compare(after, before)
        power = after.expenses[0].children[0].children[0]
        assert power.previous == Decimal(150)


@pytest.mark.django_db
class TestCopyYear:
    def test_copy_with_revaluation(self, lines):
        rental = Property.objects.create(
            name="Rental",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2000, 1, 1),
        )
        lines.excluded_properties.add(rental)
        lines.notes = "Notes"
        lines.save()
        target = copy_year(lines, YEAR + 1, Decimal("2.5"))
        assert target.year == YEAR + 1
        assert target.notes == "Notes"
        assert not target.include_properties
        assert list(target.excluded_properties.all()) == [rental]
        amounts = {line.label: line.amount.amount for line in target.lines.all()}
        assert amounts["Salary A"] == Decimal("30750.00")
        assert amounts["Power"] == Decimal("2460.00")
        assert (
            target.lines.get(label="Salary A").person
            == lines.lines.get(label="Salary A").person
        )


@pytest.mark.django_db
class TestMonthlyExpenses:
    def test_from_the_latest_budget(self, lines):
        assert budget_monthly_expenses(YEAR - 1) is None
        found = budget_monthly_expenses(YEAR + 3)
        assert found is not None
        budget_year, expenses = found
        assert budget_year == lines
        assert expenses == Decimal(500)

    def test_without_expenses(self, categories, budget_year):
        add_line(budget_year, categories["salaries"], 1000)
        assert budget_monthly_expenses(YEAR) is None
