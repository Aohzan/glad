"""Tests for investment account models with net progression."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountType,
)


class InvestmentAccountProgressionTestCase(TestCase):
    """Test cases for investment account progression with deposits."""

    def setUp(self):
        """Set up test data."""
        self.account_type = InvestmentAccountType.objects.create(
            name="Test Investment Type", code="TIT"
        )

        self.account = InvestmentAccount.objects.create(
            account_type=self.account_type,
            name="Test Investment Account",
            owner="Test Owner",
            opening_cash_value=Money(1000, "EUR"),
            opening_date=datetime.date.today() - datetime.timedelta(days=60),
        )

    def test_progression_with_deposits(self):
        """Test progression calculation including deposits."""
        # Create cash value 30 days ago
        thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1000, "EUR"),
            value_date=thirty_days_ago,
        )

        # Create current cash value
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1300, "EUR"),
            value_date=datetime.datetime.today(),
        )

        # Create deposit during the period
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(200, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=15),
        )

        progression = self.account.get_progression(30)

        # Gross progression should be 30%: (1300 - 1000) / 1000
        self.assertEqual(progression.gross_progression, Decimal("30.0"))

        # Net progression should be 10%: (1300 - 1000 - 200) / 1000
        self.assertEqual(progression.net_progression, Decimal("10.0"))

        # CSS class should be based on net progression
        self.assertEqual(progression.css_class, "up")

    def test_progression_without_deposits(self):
        """Test progression calculation without deposits."""
        # Create cash value 30 days ago
        thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1000, "EUR"),
            value_date=thirty_days_ago,
        )

        # Create current cash value
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1100, "EUR"),
            value_date=datetime.datetime.today(),
        )

        progression = self.account.get_progression(30)

        # Both gross and net progression should be the same (10%)
        self.assertEqual(progression.gross_progression, Decimal("10.0"))
        self.assertEqual(progression.net_progression, Decimal("10.0"))
        self.assertEqual(progression.css_class, "up")

    def test_progression_negative_net_with_deposits(self):
        """Test case where net progression is negative due to large deposits."""
        # Create cash value 30 days ago
        thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1000, "EUR"),
            value_date=thirty_days_ago,
        )

        # Create current cash value (small increase)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1050, "EUR"),
            value_date=datetime.datetime.today(),
        )

        # Create large deposit during the period
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(100, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=15),
        )

        progression = self.account.get_progression(30)

        # Gross progression: (1050 - 1000) / 1000 = 5%
        self.assertEqual(progression.gross_progression, Decimal("5.0"))

        # Net progression: (1050 - 1000 - 100) / 1000 = -5%
        self.assertEqual(progression.net_progression, Decimal("-5.0"))

        # CSS class should be "down" based on negative net progression
        self.assertEqual(progression.css_class, "down")

    def test_multiple_deposits_in_period(self):
        """Test progression calculation with multiple deposits."""
        # Create cash value 30 days ago
        thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1000, "EUR"),
            value_date=thirty_days_ago.date(),
        )

        # Create current cash value
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1400, "EUR"),
            value_date=datetime.datetime.today(),
        )

        # Create multiple deposits during the period
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(150, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=20),
        )
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(100, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=10),
        )

        progression = self.account.get_progression(30)

        # Gross progression: (1400 - 1000) / 1000 = 40%
        self.assertEqual(progression.gross_progression, Decimal("40.0"))

        # Net progression: (1400 - 1000 - 250) / 1000 = 15%
        self.assertEqual(progression.net_progression, Decimal("15.0"))

    def test_deposits_outside_period_not_counted(self):
        """Test that deposits outside the period are not counted."""
        # Create cash value 30 days ago
        thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1000, "EUR"),
            value_date=thirty_days_ago.date(),
        )

        # Create current cash value
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(1200, "EUR"),
            value_date=datetime.datetime.today(),
        )

        # Create deposit outside the 30-day period (35 days ago)
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(100, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=35),
        )

        # Create deposit inside the period
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(50, "EUR"),
            deposit_date=datetime.datetime.today() - datetime.timedelta(days=15),
        )

        progression = self.account.get_progression(30)

        # Only the deposit from 15 days ago should be counted
        # Net progression: (1200 - 1000 - 50) / 1000 = 15%
        self.assertEqual(progression.net_progression, Decimal("15.0"))
