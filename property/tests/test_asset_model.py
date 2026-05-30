"""Tests for property/models/asset.py - uncovered lines."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyValue


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Asset Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(300000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.mark.django_db
class TestPropertyLoanStr:
    def test_str_with_name(self, loan):
        result = str(loan)
        assert "Asset Test Property" in result
        assert "Test Loan" in result

    def test_str_without_name(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            name=None,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(100000, "EUR"),
            monthly_payment=Money(500, "EUR"),
            interest_rate=Decimal("1.0"),
        )
        result = str(loan)
        assert "Asset Test Property" in result
        assert "100,000" in result


@pytest.mark.django_db
class TestPropertyLoanGetDurationMonths:
    def test_duration_months(self, loan):
        # 2020-01-01 to 2040-01-01 = 240 months
        assert loan.get_duration_months() == 240

    def test_duration_months_none_dates(self, property_obj):
        loan = PropertyLoan(
            property=property_obj,
            start_date=None,
            end_date=None,
            original_amount=Money(100000, "EUR"),
        )
        assert loan.get_duration_months() == 0


@pytest.mark.django_db
class TestPropertyLoanComputeMonthlyPayment:
    def test_compute_monthly_payment(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(200000, "EUR"),
            interest_rate=Decimal("2.0"),
            insurance_rate=Decimal("0.2"),
        )
        loan.compute_monthly_payment()
        assert loan.monthly_payment is not None
        assert loan.monthly_payment.amount > 0
        assert loan.insurance is not None

    def test_compute_monthly_payment_no_insurance(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(200000, "EUR"),
            interest_rate=Decimal("2.0"),
            insurance_rate=Decimal("0.0"),
        )
        loan.compute_monthly_payment()
        assert loan.monthly_payment is not None
        # insurance_rate is 0, so insurance should not be set
        assert loan.insurance is None


@pytest.mark.django_db
class TestPropertyLoanTaegRate:
    def test_taeg_rate_standard_loan(self, loan):
        taeg = loan.taeg_rate()
        assert taeg > Decimal("0")

    def test_taeg_rate_no_monthly_payment_returns_zero(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(100000, "EUR"),
            monthly_payment=None,
            interest_rate=Decimal("1.0"),
        )
        assert loan.taeg_rate() == Decimal("0.0")

    def test_taeg_rate_same_year_returns_zero(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 12, 31),
            original_amount=Money(100000, "EUR"),
            monthly_payment=Money(500, "EUR"),
            interest_rate=Decimal("1.0"),
        )
        assert loan.taeg_rate() == Decimal("0.0")


@pytest.mark.django_db
class TestPropertyLoanRemainingBalance:
    def test_remaining_balance_before_start(self, loan):
        balance = loan.remaining_balance(datetime.date(2019, 1, 1))
        assert balance.amount == loan.original_amount.amount

    def test_remaining_balance_after_end(self, loan):
        balance = loan.remaining_balance(datetime.date(2041, 1, 1))
        assert balance.amount == Decimal("0")

    def test_remaining_balance_mid_loan(self, loan):
        balance = loan.remaining_balance(datetime.date(2030, 1, 1))
        assert Decimal("0") < balance.amount < loan.original_amount.amount

    def test_remaining_balance_no_payment_sequence(self, property_obj):
        loan = PropertyLoan.objects.create(
            property=property_obj,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(100000, "EUR"),
            monthly_payment=None,
            interest_rate=Decimal("0.0"),
        )
        balance = loan.remaining_balance(datetime.date(2030, 1, 1))
        # Fallback linear approximation
        assert Decimal("0") < balance.amount < Decimal("100000")


@pytest.mark.django_db
class TestPropertyLoanAmountPaid:
    def test_amount_paid(self, loan):
        paid = loan.amount_paid()
        assert paid.amount >= Decimal("0")
        assert paid.amount <= loan.original_amount.amount


@pytest.mark.django_db
class TestPropertyModel:
    def test_currency_property(self, property_obj):
        assert property_obj.currency == "EUR"

    def test_icon_house(self, property_obj):
        assert property_obj.icon == "house"

    def test_icon_apartment(self):
        prop = Property(property_type=Property.APARTMENT)
        assert prop.icon == "building"

    def test_icon_condo(self):
        prop = Property(property_type=Property.CONDO)
        assert prop.icon == "building"

    def test_icon_land(self):
        prop = Property(property_type=Property.LAND)
        assert prop.icon == "tree"

    def test_icon_other(self):
        prop = Property(property_type=Property.OTHER)
        assert prop.icon == "question-circle"

    def test_get_value_no_valuations(self, property_obj):
        value = property_obj.get_value()
        assert value.amount == Decimal("300000")

    def test_get_value_with_valuation(self, property_obj):
        PropertyValue.objects.create(
            property=property_obj,
            value=Money(350000, "EUR"),
            valuation_date=datetime.date(2023, 1, 1),
        )
        value = property_obj.get_value()
        assert value.amount == Decimal("350000")

    def test_get_value_with_max_date(self, property_obj):
        PropertyValue.objects.create(
            property=property_obj,
            value=Money(350000, "EUR"),
            valuation_date=datetime.date(2023, 1, 1),
        )
        # Before the valuation date, should return buying_value
        value = property_obj.get_value(max_date=datetime.datetime(2022, 1, 1))
        assert value.amount == Decimal("300000")

    def test_total_remaining_loans_no_loans(self, property_obj):
        total = property_obj.total_remaining_loans
        assert total.amount == Decimal("0")

    def test_total_remaining_loans_with_loan(self, property_obj, loan):
        total = property_obj.total_remaining_loans
        assert total.amount > Decimal("0")

    def test_total_paid_loans_no_loans(self, property_obj):
        total = property_obj.total_paid_loans
        assert total.amount == Decimal("0")

    def test_total_paid_loans_with_loan(self, property_obj, loan):
        total = property_obj.total_paid_loans
        assert total.amount >= Decimal("0")

    def test_gross_value(self, property_obj):
        assert property_obj.gross_value.amount == Decimal("300000")

    def test_net_value(self, property_obj, loan):
        net = property_obj.net_value
        assert net.amount >= Decimal("0")
        assert net.amount <= property_obj.gross_value.amount

    def test_net_value_at_date(self, property_obj, loan):
        net = property_obj.net_value_at_date(datetime.date(2030, 1, 1))
        assert net.amount >= Decimal("0")

    def test_get_progression_no_years(self, property_obj):
        progression = property_obj.get_progression()
        assert progression is not None

    def test_get_progression_with_years(self, property_obj):
        progression = property_obj.get_progression(years=1)
        assert progression is not None

    def test_get_progression_with_fees(self):
        prop = Property.objects.create(
            name="Fees Property",
            property_type=Property.APARTMENT,
            buying_value=Money(200000, "EUR"),
            notary_fees=Money(15000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        progression = prop.get_progression()
        # buying_value_gross = 215000; no PropertyValue → gross_value = buying_value = 200000
        # difference should be negative (current < acquisition cost)
        assert progression is not None
        assert progression.difference.amount < Decimal("0")

    def test_str(self, property_obj):
        assert str(property_obj) == "Asset Test Property"

    def test_total_remaining_loans_at_date(self, property_obj, loan):
        total = property_obj.total_remaining_loans_at_date(datetime.date(2030, 1, 1))
        assert total.amount > Decimal("0")

    def test_buying_value_gross_no_fees(self, property_obj):
        """When no fees are set, buying_value_gross equals buying_value."""
        assert property_obj.buying_value_gross.amount == Decimal("300000")
        assert (
            property_obj.buying_value_gross.currency
            == property_obj.buying_value.currency
        )

    def test_buying_value_gross_with_all_fees(self):
        prop = Property.objects.create(
            name="Fees Property",
            property_type=Property.APARTMENT,
            buying_value=Money(200000, "EUR"),
            notary_fees=Money(15000, "EUR"),
            agency_fees=Money(5000, "EUR"),
            other_fees=Money(500, "EUR"),
            credit_fees=Money(1000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        assert prop.buying_value_gross.amount == Decimal("221500")

    def test_buying_value_gross_partial_fees(self):
        prop = Property.objects.create(
            name="Partial Fees",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            notary_fees=Money(8000, "EUR"),
            buying_date=datetime.date(2021, 1, 1),
        )
        assert prop.buying_value_gross.amount == Decimal("108000")

    def test_cash_deposit_no_loans(self, property_obj):
        """With no loans, cash_deposit equals buying_value_gross."""
        assert (
            property_obj.cash_deposit.amount == property_obj.buying_value_gross.amount
        )

    def test_cash_deposit_with_loan(self, property_obj, loan):
        deposit = property_obj.cash_deposit
        expected = property_obj.buying_value_gross.amount - loan.original_amount.amount
        assert deposit.amount == expected

    def test_cash_deposit_with_fees_and_loan(self):
        prop = Property.objects.create(
            name="Deposit Test",
            property_type=Property.HOUSE,
            buying_value=Money(200000, "EUR"),
            notary_fees=Money(15000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        PropertyLoan.objects.create(
            property=prop,
            original_amount=Money(150000, "EUR"),
            interest_rate=Decimal("1.5"),
            insurance_rate=Decimal("0"),
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            monthly_payment=Money(Decimal("750.00"), "EUR"),
        )
        # gross = 215000, loan = 150000, deposit = 65000
        assert prop.cash_deposit.amount == Decimal("65000")
