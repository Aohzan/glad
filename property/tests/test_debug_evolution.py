"""Debug test to examine the property evolution issue."""

import datetime
from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyLoan


class PropertyEvolutionDebugTest(TestCase):
    """Debug test for property evolution issue."""

    def setUp(self):
        """Set up test data."""
        # Create a property that was bought 2 years ago
        self.property = Property.objects.create(
            name="Debug House",
            property_type=Property.HOUSE,
            buying_value=Money(400000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),  # 2+ years ago
            is_active=True,
        )

        # Create a loan that started 2+ years ago
        self.loan = PropertyLoan.objects.create(
            property=self.property,
            name="Debug Mortgage",
            lender="Debug Bank",
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2042, 1, 1),  # 20 years
            original_amount=Money(300000, "EUR"),
            monthly_payment=Money(1400, "EUR"),
        )

    def test_examine_view_logic(self):
        """Examine what the view logic produces."""
        print("=== DEBUG: Property Evolution Analysis ===")
        print(f"Property: {self.property.name}")
        print(f"Buying date: {self.property.buying_date}")
        print(f"Buying value: {self.property.buying_value}")
        print(f"Loan start: {self.loan.start_date}")
        print(f"Loan original amount: {self.loan.original_amount}")
        print()

        # Test the evolution over several months similar to the view logic
        now = datetime.datetime.now()
        test_months = []
        net_values = []
        loan_values = []

        # Test the last 12 months
        for i in range(12, -1, -1):
            month_date = now - datetime.timedelta(days=30 * i)
            month_str = month_date.strftime("%b %Y")
            test_months.append(month_str)

            # Filter properties to those that existed at that month
            if self.property.buying_date <= month_date.date():
                try:
                    # Calculate net value at this specific month
                    net_value = self.property.net_value_at_date(month_date.date())
                    gross_value = self.property.get_value(max_date=month_date)

                    net_values.append(float(net_value.amount))

                    # Calculate loans amount for this month (gross - net)
                    loan_amount = float(gross_value.amount) - float(net_value.amount)
                    loan_values.append(loan_amount)

                    print(f"Month: {month_str}")
                    print(f"  Gross value: {gross_value}")
                    print(f"  Net value: {net_value}")
                    print(f"  Loan amount: {loan_amount}")
                    print()

                except Exception as e:
                    print(f"Error for month {month_str}: {e}")
                    net_values.append(0.0)
                    loan_values.append(0.0)
            else:
                # Property didn't exist yet
                net_values.append(0.0)
                loan_values.append(0.0)

        print(f"Net values: {net_values}")
        print(f"Loan values: {loan_values}")
        print()

        # Check for variation
        unique_net = set(net_values)
        unique_loan = set(loan_values)
        print(f"Unique net values: {len(unique_net)} -> {unique_net}")
        print(f"Unique loan values: {len(unique_loan)} -> {unique_loan}")

        # The values should show progression
        non_zero_net = [v for v in net_values if v > 0]
        non_zero_loan = [v for v in loan_values if v > 0]

        if len(non_zero_net) > 1:
            print(
                f"Net value progression: {non_zero_net[0]} -> {non_zero_net[-1]} (change: {non_zero_net[-1] - non_zero_net[0]})"
            )
        if len(non_zero_loan) > 1:
            print(
                f"Loan value progression: {non_zero_loan[0]} -> {non_zero_loan[-1]} (change: {non_zero_loan[-1] - non_zero_loan[0]})"
            )

    def test_loan_calculation_directly(self):
        """Test loan calculation directly."""
        print("=== DEBUG: Direct Loan Calculation ===")

        test_dates = [
            datetime.date(2022, 6, 1),  # 6 months after start
            datetime.date(2023, 1, 1),  # 1 year after start
            datetime.date(2024, 1, 1),  # 2 years after start
            datetime.date(2024, 12, 1),  # Recent
        ]

        for test_date in test_dates:
            remaining = self.loan.remaining_balance(test_date)
            net_value = self.property.net_value_at_date(test_date)
            gross_value = self.property.get_value(
                max_date=datetime.datetime.combine(test_date, datetime.time())
            )

            print(f"Date: {test_date}")
            print(f"  Loan remaining: {remaining}")
            print(f"  Gross value: {gross_value}")
            print(f"  Net value: {net_value}")
            print(
                f"  Calculation check: {gross_value.amount} - {remaining.amount} = {gross_value.amount - remaining.amount}"
            )
            print()
