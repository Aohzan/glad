"""Tests for the loan figures shared by the property pages."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import (
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
)
from property.services.cashflow import build_balance_sheet
from property.services.loans import (
    loan_costs_between,
    loan_costs_by_month,
    loan_rows,
    loans_chart_data,
    loans_summary,
    without_loan_entries,
)
from property.services.monthly_flows import monthly_flows
from property.utils import LoanCosts

D = datetime.date
FEBRUARY_20 = D(2020, 2, 20)


@pytest.fixture
def prop(db):
    return Property.objects.create(
        name="Flat",
        property_type=Property.APARTMENT,
        buying_value=Money(250000, "EUR"),
        buying_date=D(2020, 1, 10),
    )


@pytest.fixture
def two_loans(prop):
    """A computed loan and a loan read from a two-row bank table."""
    computed = PropertyLoan.objects.create(
        property=prop,
        name="Main",
        start_date=D(2020, 1, 15),
        end_date=D(2040, 1, 15),
        original_amount=Money(200000, "EUR"),
        monthly_payment=Money(Decimal("1159.92"), "EUR"),
        interest_rate=Decimal("3.5"),
        insurance=Money(60, "EUR"),
    )
    imported = PropertyLoan.objects.create(
        property=prop,
        name="Works",
        start_date=D(2020, 1, 20),
        end_date=D(2020, 3, 5),
        first_payment_date=D(2020, 2, 5),
        original_amount=Money(1000, "EUR"),
        interest_rate=Decimal("2.0"),
        insurance=Money(1, "EUR"),
    )
    for day, capital, interest, balance in [
        (D(2020, 2, 5), "499.00", "1.50", "501.00"),
        (D(2020, 3, 5), "501.00", "0.84", "0.00"),
    ]:
        PropertyLoanAmortizationEntry.objects.create(
            loan=imported,
            date=day,
            capital=Money(Decimal(capital), "EUR"),
            interest=Money(Decimal(interest), "EUR"),
            remaining_balance_amount=Money(Decimal(balance), "EUR"),
        )
    return computed, imported


def test_loan_costs_by_month_adds_up_the_loans(two_loans):
    computed, imported = two_loans
    months = loan_costs_by_month([computed, imported])

    assert months[(2020, 2)] == LoanCosts(
        principal=Decimal("576.59") + Decimal("499.00"),
        interest=Decimal("583.33") + Decimal("1.50"),
        insurance=Decimal(61),
    )
    assert months[(2020, 4)] == computed.schedule().installments[2].costs
    assert sum(months.values(), LoanCosts()) == (
        computed.schedule().total + imported.schedule().total
    )


def test_loan_costs_between_counts_the_due_dates_in_the_range(two_loans):
    computed, imported = two_loans
    # 5 February (the imported loan) is in the range, 15 February is not.
    costs = loan_costs_between([computed, imported], D(2020, 2, 1), D(2020, 2, 10))
    assert costs == LoanCosts(
        principal=Decimal("499.00"), interest=Decimal("1.50"), insurance=Decimal(1)
    )
    assert loan_costs_between([computed, imported], D(2019, 1, 1), D(2019, 12, 31)) == (
        LoanCosts()
    )


def _interest_statement(prop, day=FEBRUARY_20) -> PropertyLedgerEntry:
    """A ledger entry recording loan interest, as kept for the LMNP return."""
    return PropertyLedgerEntry.objects.create(
        property=prop,
        description="Interest statement",
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
        amount=Money(500, "EUR"),
        entry_date=day,
    )


def _repair(prop, day=FEBRUARY_20) -> PropertyLedgerEntry:
    return PropertyLedgerEntry.objects.create(
        property=prop,
        description="Repair",
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.MAINTENANCE,
        amount=Money(200, "EUR"),
        entry_date=day,
    )


def test_loan_entries_stay_without_a_loan(prop):
    interest = _interest_statement(prop)
    repair = _repair(prop)
    entries = PropertyLedgerEntry.objects.filter(property=prop)
    assert set(without_loan_entries(entries, prop)) == {interest, repair}


def test_loan_entries_are_left_out_with_a_loan(prop, two_loans):
    _interest_statement(prop)
    repair = _repair(prop)
    entries = PropertyLedgerEntry.objects.filter(property=prop)
    assert list(without_loan_entries(entries, prop)) == [repair]


def test_balance_sheet_counts_the_loan_costs_once(prop, two_loans):
    _interest_statement(prop)
    _repair(prop)
    result = build_balance_sheet(prop, D(2020, 2, 1), D(2020, 2, 29))
    assert result["total_expenses"] == Decimal(200)
    assert result["total_loan_interest"] == Decimal("583.33") + Decimal("1.50")


def test_monthly_flows_count_the_loan_costs_once(prop, two_loans):
    _interest_statement(prop, D(2020, 3, 20))
    flows = monthly_flows(prop, today=D(2020, 3, 31))
    computed, imported = two_loans
    # February and March, each with an installment of both loans.
    expected = [
        computed.schedule().by_month()[month].total
        + imported.schedule().by_month()[month].total
        for month in ((2020, 2), (2020, 3))
    ]
    assert flows.charges == Decimal(0)
    assert flows.loan == sum(expected) / 2


@pytest.mark.django_db
def test_cash_flow_panel_counts_the_loan_costs_once(user_client, prop, two_loans):
    _interest_statement(prop)
    _repair(prop)
    response = user_client.get(reverse("property:panel_cashflow", args=[prop.pk]))
    month = {p["x"]: p["y"] for p in response.context["cashflow_total_expenses_series"]}
    february = two_loans[0].schedule().by_month()[(2020, 2)].total + (
        two_loans[1].schedule().by_month()[(2020, 2)].total
    )
    assert month["2020-02-01"] == pytest.approx(float(february) + 200)
    labels = [s["label"] for s in response.context["cashflow_expense_by_type_series"]]
    assert labels == ["Routine maintenance"]
    assert response.context["cashflow_has_loans"] is True


def test_loan_rows_follow_the_schedules(two_loans):
    computed, imported = two_loans
    row, table_row = loan_rows([computed, imported], D(2020, 3, 1))

    assert row.next_installment == computed.schedule().installments[1]
    assert row.is_running
    assert row.monthly_payment == Money(Decimal("1159.92"), "EUR")
    assert row.monthly_insurance == Money(60, "EUR")
    assert row.capital_paid == Money(Decimal("576.59"), "EUR")
    assert row.interest_paid == Money(Decimal("583.33"), "EUR")
    assert row.insurance_paid == Money(60, "EUR")
    total = computed.schedule().total
    assert row.total_cost == Money(total.interest + total.insurance, "EUR")
    assert row.total_repaid == Money(200000 + total.interest + total.insurance, "EUR")
    assert not row.has_table

    # The table drives the payment of the second loan: its 5 March row.
    assert table_row.has_table
    assert len(table_row.entries) == 2
    assert table_row.monthly_payment == Money(Decimal("501.84"), "EUR")
    assert table_row.monthly_insurance == Money(1, "EUR")
    assert table_row.total_cost == Money(Decimal("4.34"), "EUR")


def test_loan_rows_before_and_after_the_installments(two_loans):
    computed, imported = two_loans
    row, table_row = loan_rows([computed, imported], D(2020, 1, 10))
    assert not row.is_running
    assert row.remaining_balance == Money(0, "EUR")
    assert row.capital_paid == Money(0, "EUR")
    # Not disbursed yet: the first installment is the next one.
    assert row.next_installment == computed.schedule().installments[0]

    (table_row,) = loan_rows([imported], D(2020, 4, 1))
    assert not table_row.is_running
    assert table_row.next_installment is None
    # Without a next installment, the stored amounts are shown.
    assert table_row.monthly_payment is None
    assert table_row.monthly_insurance == Money(1, "EUR")
    assert table_row.capital_paid == Money(1000, "EUR")


def test_loan_rows_of_a_sold_property(prop, two_loans):
    prop.selling_date = D(2030, 6, 20)
    prop.save()
    computed = PropertyLoan.objects.select_related("property").get(pk=two_loans[0].pk)
    (row,) = loan_rows([computed], D(2031, 1, 1))
    assert not row.is_running
    assert row.remaining_balance == Money(0, "EUR")
    assert row.capital_paid == Money(200000, "EUR")
    assert row.interest_paid.amount == computed.schedule().total.interest


def test_loans_summary_adds_the_running_loans(two_loans):
    computed, imported = two_loans
    rows = loan_rows([computed, imported], D(2020, 3, 1))
    summary = loans_summary(rows, "EUR")
    assert summary.total_mensuality == Money(
        Decimal("1159.92") + 60 + Decimal("501.84") + 1, "EUR"
    )
    assert summary.total_remaining == Money(
        computed.schedule().balance_at(D(2020, 3, 1)) + Decimal("501.00"), "EUR"
    )
    assert summary.total_capital_paid == Money(Decimal("576.59") + 499, "EUR")

    # Once the second loan is repaid, only the first counts.
    later = loans_summary(loan_rows([computed, imported], D(2020, 3, 6)), "EUR")
    assert later.total_mensuality == Money(Decimal("1219.92"), "EUR")


def test_loans_summary_without_loans():
    summary = loans_summary([], "EUR")
    assert summary.total_mensuality == Money(0, "EUR")
    assert summary.total_remaining == Money(0, "EUR")


def test_chart_series_share_the_months_of_all_loans(two_loans):
    computed, imported = two_loans
    data = loans_chart_data([computed, imported], "EUR")

    assert data["currency"] == "EUR"
    main, works = data["loans"]
    assert main["name"] == "Main"
    assert works["name"] == "Works"
    # Both series cover February 2020 to January 2040, the second one with
    # zeros after its last installment, so the stacked bars line up by date.
    assert [p["x"] for p in main["data"]] == [p["x"] for p in works["data"]]
    assert main["data"][0] == {"x": "2020-02-01", "y": float(Decimal("1219.92"))}
    # The imported table carries the loan insurance too.
    assert works["data"][:3] == [
        {"x": "2020-02-01", "y": float(Decimal("501.50"))},
        {"x": "2020-03-01", "y": float(Decimal("502.84"))},
        {"x": "2020-04-01", "y": 0.0},
    ]
    assert data["total_capital"][0] == {
        "x": "2020-02-01",
        "y": float(Decimal("576.59") + 499),
    }
    assert data["total_interest"][0] == {
        "x": "2020-02-01",
        "y": float(Decimal("583.33") + Decimal("1.50")),
    }


def test_chart_names_are_unique_and_can_name_the_property(prop, two_loans):
    computed, imported = two_loans
    imported.name = "Main"
    data = loans_chart_data([computed, imported], "EUR", with_property=True)
    assert [s["name"] for s in data["loans"]] == [
        "Flat — Main",
        f"Flat — Main #{imported.pk}",
    ]


def test_chart_without_loans():
    assert loans_chart_data([], "USD") == {
        "currency": "USD",
        "loans": [],
        "total_capital": [],
        "total_interest": [],
    }


def test_prefetched_loans_are_read_once(django_assert_num_queries, prop, two_loans):
    """A schedule is built once per loan, then queried at every date for free."""
    prop = Property.objects.prefetch_related("loans__amortization_entries").get(
        pk=prop.pk
    )
    with django_assert_num_queries(0):
        balances = [
            prop.total_remaining_loans_at_date(D(2021, month, 1)).amount
            for month in range(1, 13)
        ]
    assert balances == sorted(balances, reverse=True)
