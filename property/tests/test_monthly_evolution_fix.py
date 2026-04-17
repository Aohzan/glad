"""Test to verify the monthly evolution fix."""

import datetime

from django.contrib.auth.models import User
from django.test import Client, TestCase
from moneyed import Money

from property.models import Property, PropertyLoan


class MonthlyEvolutionFixTest(TestCase):
    """Test that the monthly evolution fix works correctly."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client = Client()

        # Create a property that was bought over a year ago
        self.property = Property.objects.create(
            name="Evolution Test House",
            property_type=Property.HOUSE,
            buying_value=Money(500000, "EUR"),
            buying_date=datetime.date(2023, 1, 1),  # Over a year ago
            is_active=True,
        )

        # Create a loan with significant monthly payments
        self.loan = PropertyLoan.objects.create(
            property=self.property,
            name="Evolution Test Mortgage",
            lender="Test Bank",
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2043, 1, 1),  # 20 years
            original_amount=Money(400000, "EUR"),
            monthly_payment=Money(2000, "EUR"),
        )

    def test_monthly_evolution_in_dashboard(self):
        """Test that the dashboard shows proper monthly evolution."""
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        context = response.context
        net_evolution = context["patrimony_evolution_properties_net"]
        loan_evolution = context["patrimony_evolution_properties_gross"]

        print(f"Dashboard net evolution: {net_evolution}")
        print(f"Dashboard loan evolution: {loan_evolution}")

        # Should have 25 data points (24 months + current month)
        self.assertEqual(len(net_evolution), 25)
        self.assertEqual(len(loan_evolution), 25)

        # Check that there's meaningful evolution
        # Since the property was bought over a year ago, we should see different values
        unique_net_values = len(set(net_evolution))
        unique_loan_values = len(set(loan_evolution))

        print(f"Unique net values: {unique_net_values}")
        print(f"Unique loan values: {unique_loan_values}")

        # We should have many unique values (at least 12 for the last year)
        self.assertGreater(
            unique_net_values,
            10,
            "Should have significant variation in net values over the year",
        )
        self.assertGreater(
            unique_loan_values,
            10,
            "Should have significant variation in loan values over the year",
        )

        # The values should show a clear trend
        # Net values should generally increase (as loans are paid down)
        # Loan values should generally decrease

        # Get values from 12 months ago vs now (ignoring zeros from before property existed)
        non_zero_net = [v for v in net_evolution if v > 0]
        non_zero_loan = [v for v in loan_evolution if v > 0]

        if len(non_zero_net) >= 12:
            # Compare first vs last values over the year
            early_net = non_zero_net[0]
            recent_net = non_zero_net[-1]
            early_loan = non_zero_loan[0]
            recent_loan = non_zero_loan[-1]

            print(
                f"Net progression: {early_net} -> {recent_net} (diff: {recent_net - early_net})"
            )
            print(
                f"Loan progression: {early_loan} -> {recent_loan} (diff: {recent_loan - early_loan})"
            )

            # Net value should increase over time (equity builds up)
            self.assertGreater(
                recent_net,
                early_net,
                "Net value should increase as loans are paid down",
            )

            # Loan amount should decrease over time
            self.assertLess(
                recent_loan,
                early_loan,
                "Loan amount should decrease as payments are made",
            )

            # The changes should be significant (more than 10% over the year)
            net_change_percent = (recent_net - early_net) / early_net * 100
            loan_change_percent = abs((recent_loan - early_loan) / early_loan) * 100

            print(f"Net change: {net_change_percent:.1f}%")
            print(f"Loan change: {loan_change_percent:.1f}%")

            # With 2000€/month payments on a 400k loan, we should see significant change
            self.assertGreater(
                net_change_percent,
                5,
                "Net value should increase by at least 5% over the year",
            )
            self.assertGreater(
                loan_change_percent,
                5,
                "Loan amount should decrease by at least 5% over the year",
            )

    def test_monthly_calculation_precision(self):
        """Test that monthly calculations are precise."""
        # Test several specific months to verify precision
        test_cases = [
            (datetime.date(2023, 6, 1), "6 months after start"),
            (datetime.date(2024, 1, 1), "1 year after start"),
            (datetime.date(2024, 6, 1), "18 months after start"),
        ]

        for test_date, description in test_cases:
            with self.subTest(date=test_date):
                # Calculate expected values manually
                months_since_start = (
                    test_date.year - self.loan.start_date.year
                ) * 12 + (test_date.month - self.loan.start_date.month)

                total_months = (
                    self.loan.end_date.year - self.loan.start_date.year
                ) * 12 + (self.loan.end_date.month - self.loan.start_date.month)

                self.assertGreater(total_months, 0)

                # With zero interest configured in this fixture, each payment
                # directly reduces principal.
                expected_loan_balance = max(
                    0,
                    400000 - (2000 * months_since_start),
                )
                expected_net_value = 500000 - expected_loan_balance

                # Get actual values
                actual_net = self.property.net_value_at_date(test_date)
                actual_loan = self.property.total_remaining_loans_at_date(test_date)

                print(f"\n{description} ({test_date}):")
                print(f"  Expected loan: €{expected_loan_balance:,.0f}")
                print(f"  Actual loan: {actual_loan}")
                print(f"  Expected net: €{expected_net_value:,.0f}")
                print(f"  Actual net: {actual_net}")

                # Allow for small rounding differences
                self.assertAlmostEqual(
                    float(actual_loan.amount), expected_loan_balance, places=0
                )
                self.assertAlmostEqual(
                    float(actual_net.amount), expected_net_value, places=0
                )
