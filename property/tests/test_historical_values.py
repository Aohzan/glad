"""Tests for property historical values calculation."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyLoan


class PropertyHistoricalValuesTest(TestCase):
    """Test property historical values calculations."""

    def setUp(self):
        """Set up test data."""
        # Create a test property
        self.property = Property.objects.create(
            name="Test Property",
            property_type=Property.HOUSE,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date(2023, 1, 1),
            is_active=True,
        )

        # Create a test loan
        self.loan = PropertyLoan.objects.create(
            property=self.property,
            name="Test Loan",
            lender="Test Bank",
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2033, 1, 1),  # 10 years
            original_amount=Money(150000, "EUR"),
            monthly_payment=Money(1500, "EUR"),
        )

    def test_loan_remaining_balance_historical(self):
        """Test that loan remaining balance changes over time."""
        # Test at start date
        start_balance = self.loan.remaining_balance(datetime.date(2023, 1, 1))
        self.assertEqual(start_balance.amount, Decimal("150000"))

        # Test at 1 year later (12 months paid)
        one_year_later = self.loan.remaining_balance(datetime.date(2024, 1, 1))
        # With zero interest, each monthly payment repays principal directly.
        expected_remaining = Decimal("150000") - (Decimal("1500") * Decimal("12"))
        self.assertEqual(one_year_later.amount, expected_remaining)

        # Test at 5 years later (60 months paid)
        five_years_later = self.loan.remaining_balance(datetime.date(2028, 1, 1))
        expected_remaining = Decimal("150000") - (Decimal("1500") * Decimal("60"))
        self.assertEqual(five_years_later.amount, expected_remaining)

        # Test at end date
        end_balance = self.loan.remaining_balance(datetime.date(2033, 1, 1))
        self.assertEqual(end_balance.amount, Decimal("0"))

    def test_property_net_value_historical(self):
        """Test that property net value changes over time due to loan payments."""
        # Gross value should be constant (buying value) since no PropertyValue records
        gross_value = Decimal("200000")

        # Test at start date
        start_net = self.property.net_value_at_date(datetime.date(2023, 1, 1))
        expected_start_net = gross_value - Decimal("150000")  # 50000
        self.assertEqual(start_net.amount, expected_start_net)

        # Test at 1 year later
        one_year_net = self.property.net_value_at_date(datetime.date(2024, 1, 1))
        expected_one_year_net = gross_value - Decimal("132000")
        self.assertEqual(one_year_net.amount, expected_one_year_net)

        # Test at 5 years later
        five_years_net = self.property.net_value_at_date(datetime.date(2028, 1, 1))
        expected_five_years_net = gross_value - Decimal("60000")
        self.assertEqual(five_years_net.amount, expected_five_years_net)

        # Test at end date
        end_net = self.property.net_value_at_date(datetime.date(2033, 1, 1))
        expected_end_net = gross_value - Decimal("0")  # 200000 (fully paid)
        self.assertEqual(end_net.amount, expected_end_net)

    def test_property_loans_evolution(self):
        """Test that loans amount decreases over time."""
        # Test at start date
        start_loans = self.property.total_remaining_loans_at_date(
            datetime.date(2023, 1, 1)
        )
        self.assertEqual(start_loans.amount, Decimal("150000"))

        # Test progression over time
        dates_and_expected = [
            (datetime.date(2024, 1, 1), Decimal("132000")),  # 1 year
            (datetime.date(2025, 1, 1), Decimal("114000")),  # 2 years
            (datetime.date(2028, 1, 1), Decimal("60000")),  # 5 years
            (datetime.date(2033, 1, 1), Decimal("0")),  # end
        ]

        for test_date, expected_amount in dates_and_expected:
            with self.subTest(date=test_date):
                loans_amount = self.property.total_remaining_loans_at_date(test_date)
                self.assertEqual(loans_amount.amount, expected_amount)

    def test_chart_data_consistency(self):
        """Test that chart data shows progression over time."""
        # Simulate the chart calculation for a few months
        test_dates = [
            datetime.date(2023, 6, 1),  # 6 months
            datetime.date(2024, 1, 1),  # 12 months
            datetime.date(2024, 6, 1),  # 18 months
            datetime.date(2025, 1, 1),  # 24 months
        ]

        net_values = []
        loan_values = []

        for test_date in test_dates:
            net_value = self.property.net_value_at_date(test_date)
            loan_value = self.property.total_remaining_loans_at_date(test_date)

            net_values.append(float(net_value.amount))
            loan_values.append(float(loan_value.amount))

        # Net values should increase over time (as loans are paid down)
        for i in range(1, len(net_values)):
            self.assertGreater(
                net_values[i],
                net_values[i - 1],
                f"Net value should increase over time. Month {i}: {net_values[i]} should be > Month {i - 1}: {net_values[i - 1]}",
            )

        # Loan values should decrease over time
        for i in range(1, len(loan_values)):
            self.assertLess(
                loan_values[i],
                loan_values[i - 1],
                f"Loan value should decrease over time. Month {i}: {loan_values[i]} should be < Month {i - 1}: {loan_values[i - 1]}",
            )
