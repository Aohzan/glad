"""Tests for finance utils."""

from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from finance.utils import AccountProgression


class AccountProgressionTestCase(TestCase):
    """Test cases for AccountProgression class."""

    def test_basic_progression_calculation(self):
        """Test basic progression calculation without deposits."""
        current_value = Money(1100, "EUR")
        old_value = Money(1000, "EUR")

        progression = AccountProgression(current_value, old_value)

        self.assertEqual(progression.gross_progression, Decimal("10.0"))
        self.assertEqual(progression.gross_difference.amount, Decimal("100"))
        self.assertEqual(progression.net_progression, Decimal("10.0"))
        self.assertEqual(progression.net_difference.amount, Decimal("100"))
        self.assertEqual(progression.css_class, "up")

    def test_progression_with_deposits(self):
        """Test progression calculation with deposits excluded."""
        current_value = Money(1300, "EUR")  # Current value
        old_value = Money(1000, "EUR")  # Old value
        deposits = Money(200, "EUR")  # Deposits made during period

        progression = AccountProgression(current_value, old_value, deposits)

        # Gross progression: (1300 - 1000) / 1000 = 30%
        self.assertEqual(progression.gross_progression, Decimal("30.0"))
        self.assertEqual(progression.gross_difference.amount, Decimal("300"))

        # Net progression: (1300 - 1000 - 200) / 1000 = 10%
        self.assertEqual(progression.net_progression, Decimal("10.0"))
        self.assertEqual(progression.net_difference.amount, Decimal("100"))
        self.assertEqual(progression.css_class, "up")

    def test_negative_progression_with_deposits(self):
        """Test negative net progression even with deposits."""
        current_value = Money(1050, "EUR")  # Current value
        old_value = Money(1000, "EUR")  # Old value
        deposits = Money(100, "EUR")  # Deposits made during period

        progression = AccountProgression(current_value, old_value, deposits)

        # Gross progression: (1050 - 1000) / 1000 = 5%
        self.assertEqual(progression.gross_progression, Decimal("5.0"))
        self.assertEqual(progression.gross_difference.amount, Decimal("50"))

        # Net progression: (1050 - 1000 - 100) / 1000 = -5%
        self.assertEqual(progression.net_progression, Decimal("-5.0"))
        self.assertEqual(progression.net_difference.amount, Decimal("-50"))
        self.assertEqual(progression.css_class, "down")

    def test_zero_old_value(self):
        """Test progression calculation when old value is zero."""
        current_value = Money(100, "EUR")
        old_value = Money(0, "EUR")
        deposits = Money(50, "EUR")

        progression = AccountProgression(current_value, old_value, deposits)

        # When old value is 0, progression should be 100% for positive current value
        self.assertEqual(progression.gross_progression, Decimal("100.0"))
        self.assertEqual(progression.net_progression, Decimal("100.0"))
        self.assertEqual(progression.css_class, "up")

    def test_no_deposits_parameter(self):
        """Test that deposits parameter defaults to zero when not provided."""
        current_value = Money(1100, "EUR")
        old_value = Money(1000, "EUR")

        progression = AccountProgression(current_value, old_value)

        # Should be the same as providing zero deposits
        self.assertEqual(progression.gross_progression, progression.net_progression)
        self.assertEqual(
            progression.gross_difference.amount, progression.net_difference.amount
        )

    def test_css_class_neutral(self):
        """Test CSS class for neutral progression."""
        current_value = Money(1000, "EUR")
        old_value = Money(1000, "EUR")
        deposits = Money(50, "EUR")

        progression = AccountProgression(current_value, old_value, deposits)

        # Net progression: (1000 - 1000 - 50) / 1000 = -5%, but net difference rounds to -50
        self.assertEqual(progression.net_difference.amount, Decimal("-50"))
        self.assertEqual(progression.css_class, "down")

    def test_invalid_input_types(self):
        """Test that invalid input types raise TypeError."""
        with self.assertRaises(TypeError):
            AccountProgression("not_money", Money(100, "EUR"))

        with self.assertRaises(TypeError):
            AccountProgression(Money(100, "EUR"), "not_money")

        with self.assertRaises(TypeError):
            AccountProgression(Money(100, "EUR"), Money(100, "EUR"), "not_money")

    def test_string_representation(self):
        """Test string representation of AccountProgression."""
        current_value = Money(1100, "EUR")
        old_value = Money(1000, "EUR")
        deposits = Money(20, "EUR")

        progression = AccountProgression(current_value, old_value, deposits)

        # Should show net progression and net difference
        expected = (
            f"{progression.net_progression}% ({progression.net_difference.amount})"
        )
        self.assertEqual(str(progression), expected)
