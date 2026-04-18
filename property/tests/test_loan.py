"""Tests for property loan functionality."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyValue


class PropertyLoanTestCase(TestCase):
    """Test cases for PropertyLoan model."""

    def setUp(self):
        """Set up test data."""
        self.property = Property.objects.create(
            name="Test Property",
            address="123 Test Street",
            property_type=Property.HOUSE,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date.today() - datetime.timedelta(days=365),
        )

        self.loan = PropertyLoan.objects.create(
            property=self.property,
            name="Test Loan",
            start_date=datetime.date.today() - datetime.timedelta(days=180),
            end_date=datetime.date.today() + datetime.timedelta(days=3650),  # 10 years
            original_amount=Money(150000, "EUR"),
            monthly_payment=Money(500, "EUR"),
            interest_rate=Decimal("2.5"),
        )

        self.short_loan = PropertyLoan.objects.create(
            property=self.property,
            name="Short Loan",
            start_date=datetime.date.today() - datetime.timedelta(days=90),
            end_date=datetime.date.today()
            + datetime.timedelta(days=90),  # 6 months total
            original_amount=Money(10000, "EUR"),
            monthly_payment=Money(100, "EUR"),
        )

    def test_loan_creation(self):
        """Test basic loan creation."""
        self.assertEqual(self.loan.property, self.property)
        self.assertEqual(self.loan.name, "Test Loan")
        self.assertEqual(float(self.loan.original_amount.amount), 150000.0)
        self.assertEqual(self.loan.interest_rate, Decimal("2.5"))
        self.assertEqual(float(self.loan.monthly_payment.amount), 500.0)

    def test_loan_nullable_monthly_payment(self):
        """Test that monthly_payment can be null."""
        loan = PropertyLoan.objects.create(
            property=self.property,
            name="No Payment Loan",
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=365),
            original_amount=Money(50000, "EUR"),
            interest_rate=Decimal("1.5"),
        )
        self.assertIsNone(loan.monthly_payment)
        self.assertIsNone(loan.insurance)

    def test_string_representation(self):
        """Test string representation of PropertyLoan."""
        self.assertEqual(str(self.loan), "Test Property - Test Loan")

        # Test loan without name
        unnamed_loan = PropertyLoan.objects.create(
            property=self.property,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=365),
            original_amount=Money(5000, "EUR"),
            monthly_payment=Money(50, "EUR"),
        )
        self.assertTrue(str(unnamed_loan).startswith("Test Property -"))

    def test_get_duration_months(self):
        """Test get_duration_months method."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),
        )
        self.assertEqual(loan.get_duration_months(), 240)

    def test_get_duration_months_none_dates(self):
        """Test get_duration_months returns 0 when dates are None."""
        loan = PropertyLoan()
        self.assertEqual(loan.get_duration_months(), 0)

    def test_compute_monthly_payment(self):
        """Test compute_monthly_payment sets monthly_payment and insurance."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),  # 240 months
            original_amount=Money(200000, "EUR"),
            interest_rate=Decimal("3.5"),
            insurance_rate=Decimal("0.36"),
        )
        loan.compute_monthly_payment()
        # Standard French amortization: ~1159.97 for 200k at 3.5% over 240 months
        self.assertIsNotNone(loan.monthly_payment)
        self.assertAlmostEqual(float(loan.monthly_payment.amount), 1159.97, delta=1.0)
        # Insurance: 200000 * 0.36% / 12 = 60
        self.assertIsNotNone(loan.insurance)
        self.assertAlmostEqual(float(loan.insurance.amount), 60.0, delta=0.5)

    def test_compute_monthly_payment_zero_rate(self):
        """Test compute_monthly_payment with zero interest rate."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2026, 1, 1),  # 24 months
            original_amount=Money(24000, "EUR"),
            interest_rate=Decimal("0"),
        )
        loan.compute_monthly_payment()
        self.assertIsNotNone(loan.monthly_payment)
        self.assertAlmostEqual(float(loan.monthly_payment.amount), 1000.0, delta=0.01)

    def test_compute_monthly_payment_no_insurance_rate(self):
        """Test compute_monthly_payment without insurance rate."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),
            original_amount=Money(100000, "EUR"),
            interest_rate=Decimal("2.0"),
        )
        loan.compute_monthly_payment()
        self.assertIsNotNone(loan.monthly_payment)
        self.assertIsNone(loan.insurance)

    def test_compute_monthly_payment_missing_data(self):
        """Test compute_monthly_payment does nothing when data is missing."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),
        )
        loan.compute_monthly_payment()
        self.assertIsNone(loan.monthly_payment)

    def test_taeg_rate_with_null_monthly_payment(self):
        """Test taeg_rate returns 0 when monthly_payment is None."""
        loan = PropertyLoan(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),
            original_amount=Money(100000, "EUR"),
        )
        self.assertEqual(loan.taeg_rate(), Decimal("0.0"))

    def test_remaining_balance_future_loan(self):
        """Test remaining balance for a loan that hasn't started yet."""
        future_loan = PropertyLoan.objects.create(
            property=self.property,
            name="Future Loan",
            start_date=datetime.date.today() + datetime.timedelta(days=30),
            end_date=datetime.date.today() + datetime.timedelta(days=365),
            original_amount=Money(20000, "EUR"),
            monthly_payment=Money(200, "EUR"),
        )

        self.assertEqual(future_loan.remaining_balance().amount, Decimal("20000"))

    def test_remaining_balance_completed_loan(self):
        """Test remaining balance for a completed loan."""
        completed_loan = PropertyLoan.objects.create(
            property=self.property,
            name="Completed Loan",
            start_date=datetime.date.today() - datetime.timedelta(days=365),
            end_date=datetime.date.today() - datetime.timedelta(days=1),
            original_amount=Money(20000, "EUR"),
            monthly_payment=Money(200, "EUR"),
        )

        self.assertEqual(completed_loan.remaining_balance().amount, Decimal("0"))

    def test_remaining_balance_active_loan(self):
        """Test remaining balance for an active loan.

        The short_loan has no interest_rate, monthly_payment=100, original_amount=10000,
        6-month term (90 days ago → +90 days), so ~3 months have elapsed.
        With real amortization and zero interest: balance = 10000 - 3×100 = 9700.
        """
        remaining = self.short_loan.remaining_balance().amount
        # Real amortization: ~3 months × 100 = 300 paid → ~9700 remaining
        self.assertGreaterEqual(remaining, Decimal("9500"))  # Lower bound
        self.assertLessEqual(remaining, Decimal("10000"))  # Upper bound

    def test_amount_paid(self):
        """Test amount paid calculation.

        The short_loan has no interest_rate, monthly_payment=100, original_amount=10000.
        After ~3 months: paid = ~300 (real amortization, no interest).
        """
        paid = self.short_loan.amount_paid().amount
        # Real amortization: ~3 months × 100 = ~300 paid
        self.assertGreaterEqual(paid, Decimal("0"))  # Lower bound
        self.assertLessEqual(paid, Decimal("500"))  # Upper bound

        # Original amount minus remaining should equal amount paid
        self.assertAlmostEqual(
            float(self.short_loan.original_amount.amount)
            - float(self.short_loan.remaining_balance().amount),
            float(self.short_loan.amount_paid().amount),
            places=2,
        )


class PropertyWithLoansTestCase(TestCase):
    """Test cases for Property model with loan functionality."""

    def setUp(self):
        """Set up test data."""
        self.property = Property.objects.create(
            name="Test Property",
            address="123 Test Street",
            property_type=Property.HOUSE,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date.today() - datetime.timedelta(days=365),
        )

        # Add a property valuation
        PropertyValue.objects.create(
            property=self.property,
            value=Money(250000, "EUR"),
            valuation_date=datetime.date.today(),
        )

        # Create two loans for the property
        self.loan1 = PropertyLoan.objects.create(
            property=self.property,
            name="Loan 1",
            start_date=datetime.date.today() - datetime.timedelta(days=180),
            end_date=datetime.date.today() + datetime.timedelta(days=3650),  # 10 years
            original_amount=Money(100000, "EUR"),
            monthly_payment=Money(400, "EUR"),
        )

        self.loan2 = PropertyLoan.objects.create(
            property=self.property,
            name="Loan 2",
            start_date=datetime.date.today() - datetime.timedelta(days=90),
            end_date=datetime.date.today() + datetime.timedelta(days=1825),  # 5 years
            original_amount=Money(50000, "EUR"),
            monthly_payment=Money(300, "EUR"),
        )

    def test_total_remaining_loans(self):
        """Test total remaining loans calculation."""
        total_remaining = self.property.total_remaining_loans.amount

        # Should be close to the sum of both loans' remaining balances
        expected = (
            self.loan1.remaining_balance().amount
            + self.loan2.remaining_balance().amount
        )
        self.assertAlmostEqual(float(total_remaining), float(expected), places=2)

    def test_total_paid_loans(self):
        """Test total paid loans calculation."""
        total_paid = self.property.total_paid_loans.amount

        # Should be close to the sum of both loans' paid amounts
        expected = self.loan1.amount_paid().amount + self.loan2.amount_paid().amount
        self.assertAlmostEqual(float(total_paid), float(expected), places=2)

    def test_gross_value(self):
        """Test gross value property."""
        self.assertEqual(self.property.gross_value.amount, Decimal("250000"))
        self.assertEqual(str(self.property.gross_value.currency), "EUR")

    def test_net_value(self):
        """Test net value property."""
        # Net value should be gross value minus remaining loans
        expected = (
            self.property.gross_value.amount
            - self.property.total_remaining_loans.amount
        )
        self.assertEqual(self.property.net_value.amount, expected)

    def test_net_value_with_no_loans(self):
        """Test net value property with no loans."""
        property_no_loans = Property.objects.create(
            name="No Loans Property",
            address="456 Test Avenue",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date.today(),
        )

        PropertyValue.objects.create(
            property=property_no_loans,
            value=Money(120000, "EUR"),
            valuation_date=datetime.date.today(),
        )

        # Net value should equal gross value when no loans
        self.assertEqual(
            property_no_loans.net_value.amount, property_no_loans.gross_value.amount
        )
        self.assertEqual(property_no_loans.total_remaining_loans.amount, Decimal("0"))

    def test_net_value_with_loans_exceeding_value(self):
        """Test net value property when loans exceed property value."""
        property_underwater = Property.objects.create(
            name="Underwater Property",
            address="789 Test Blvd",
            property_type=Property.HOUSE,
            buying_value=Money(300000, "EUR"),
            buying_date=datetime.date.today(),
        )

        # Property value decreased
        PropertyValue.objects.create(
            property=property_underwater,
            value=Money(250000, "EUR"),
            valuation_date=datetime.date.today(),
        )

        # Large loan
        PropertyLoan.objects.create(
            property=property_underwater,
            name="Large Loan",
            start_date=datetime.date.today() - datetime.timedelta(days=30),
            end_date=datetime.date.today() + datetime.timedelta(days=3650),
            original_amount=Money(280000, "EUR"),
            monthly_payment=Money(1000, "EUR"),
        )

        # Net value should not go below zero
        self.assertEqual(property_underwater.net_value.amount, Decimal("0"))
