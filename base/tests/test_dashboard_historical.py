"""Tests for the dashboard view with property historical data."""

import datetime

from django.contrib.auth.models import User
from django.test import Client, TestCase
from moneyed import Money

from property.models import Property, PropertyLoan


class DashboardHistoricalDataTest(TestCase):
    """Test the dashboard view with historical property data."""

    def setUp(self):
        """Set up test data."""
        # Create a test user
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client = Client()

        # Create a test property with loan
        self.property = Property.objects.create(
            name="Test House",
            property_type=Property.HOUSE,
            buying_value=Money(300000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),  # 2+ years ago
            is_active=True,
        )

        # Create a loan that started 2+ years ago
        self.loan = PropertyLoan.objects.create(
            property=self.property,
            name="Mortgage",
            lender="Test Bank",
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2042, 1, 1),  # 20 years
            original_amount=Money(250000, "EUR"),
            monthly_payment=Money(1200, "EUR"),
        )

    def test_dashboard_property_evolution_data(self):
        """Test that the dashboard provides property evolution data that changes over time."""
        # Log in the user
        self.client.login(username="testuser", password="testpass123")

        # Get the dashboard view
        response = self.client.get("/")  # Base URL since no namespace
        self.assertEqual(response.status_code, 200)

        # Check that context contains the evolution data
        context = response.context
        self.assertIn("patrimony_evolution_properties_net", context)
        self.assertIn("patrimony_evolution_properties_gross", context)

        # Get the evolution data
        net_evolution = context["patrimony_evolution_properties_net"]
        loan_evolution = context["patrimony_evolution_properties_gross"]

        # Debug: print the values to see what's happening
        print(f"Net evolution: {net_evolution}")
        print(f"Loan evolution: {loan_evolution}")

        # The data should have 25 data points (24 months + current)
        self.assertEqual(len(net_evolution), 25)
        self.assertEqual(len(loan_evolution), 25)

        # Check that values are not all the same (indicating no evolution)
        unique_net_values = set(net_evolution)
        unique_loan_values = set(loan_evolution)

        print(f"Unique net values: {len(unique_net_values)}")
        print(f"Unique loan values: {len(unique_loan_values)}")

        # There should be multiple unique values showing evolution
        # (unless the property was purchased very recently)
        if self.property.buying_date < datetime.date.today() - datetime.timedelta(
            days=90
        ):
            self.assertGreater(
                len(unique_net_values), 1, "Net values should show evolution over time"
            )
            self.assertGreater(
                len(unique_loan_values),
                1,
                "Loan values should show evolution over time",
            )

    def test_manual_calculation_verification(self):
        """Manually verify the calculation for specific months."""
        # Test a few specific dates
        test_dates = [
            datetime.date(2022, 6, 1),  # 6 months after start
            datetime.date(2023, 1, 1),  # 1 year after start
            datetime.date(2024, 1, 1),  # 2 years after start
        ]

        for test_date in test_dates:
            with self.subTest(date=test_date):
                # Calculate expected values
                months_since_start = (
                    test_date.year - self.loan.start_date.year
                ) * 12 + (test_date.month - self.loan.start_date.month)
                total_months = (
                    self.loan.end_date.year - self.loan.start_date.year
                ) * 12 + (self.loan.end_date.month - self.loan.start_date.month)

                if months_since_start >= 0 and months_since_start <= total_months:
                    # With no interest rate set, amortization follows fixed
                    # monthly principal payments (capped at zero balance).
                    expected_loan_balance = max(
                        0.0,
                        float(str(self.loan.original_amount.amount))
                        - (
                            float(str(self.loan.monthly_payment.amount))
                            * months_since_start
                        ),
                    )
                    expected_net_value = (
                        float(str(self.property.buying_value.amount))
                        - expected_loan_balance
                    )

                    # Get actual calculated values
                    actual_loan_balance = self.property.total_remaining_loans_at_date(
                        test_date
                    )
                    actual_net_value = self.property.net_value_at_date(test_date)

                    print(f"Date: {test_date}")
                    print(f"  Months since start: {months_since_start}")
                    print(f"  Expected loan balance: {expected_loan_balance}")
                    print(f"  Actual loan balance: {actual_loan_balance.amount}")
                    print(f"  Expected net value: {expected_net_value}")
                    print(f"  Actual net value: {actual_net_value.amount}")
                    print()

                    # Allow small rounding differences
                    self.assertAlmostEqual(
                        float(actual_loan_balance.amount),
                        expected_loan_balance,
                        places=0,
                    )
                    self.assertAlmostEqual(
                        float(actual_net_value.amount), expected_net_value, places=0
                    )
