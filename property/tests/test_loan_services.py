"""Tests for the loan figures shared by the property pages."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyLoanAmortizationEntry
from property.services.loans import loan_costs_between, loan_costs_by_month
from property.utils import LoanCosts

D = datetime.date


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
