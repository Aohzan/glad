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
