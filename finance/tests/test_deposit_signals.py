"""Tests for the new deposit and holding history features."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)


class TestSavingAccountDepositSignals(TestCase):
    """Test signals for SavingAccountDeposit."""

    def setUp(self):
        """Set up test data."""
        self.account_type = SavingAccountType.objects.create(
            name="Test Savings", code="TS"
        )
        self.account = SavingAccount.objects.create(
            account_type=self.account_type,
            name="Test Account",
            opening_value=Money(1000, "EUR"),
            opening_date=datetime.date(2023, 1, 1),
        )

    def test_deposit_creates_account_value_when_enabled(self):
        """Test that a deposit creates an account value when update_account_value is True."""
        deposit = SavingAccountDeposit.objects.create(
            account=self.account,
            amount=Money(500, "EUR"),
            deposit_date=datetime.date(2023, 2, 1),
            update_account_value=True,
        )

        # Check that a SavingAccountValue was created
        account_value = SavingAccountValue.objects.filter(
            account=self.account, value_date=deposit.deposit_date
        ).first()

        assert account_value is not None
        assert account_value.value == Money(1500, "EUR")  # 1000 + 500

    def test_deposit_does_not_create_account_value_when_disabled(self):
        """Test that a deposit doesn't create an account value when update_account_value is False."""
        SavingAccountDeposit.objects.create(
            account=self.account,
            amount=Money(500, "EUR"),
            deposit_date=datetime.date(2023, 2, 1),
            update_account_value=False,
        )

        # Check that no SavingAccountValue was created for this date
        account_value = SavingAccountValue.objects.filter(
            account=self.account, value_date=datetime.date(2023, 2, 1)
        ).first()

        assert account_value is None


class TestInvestmentAccountDepositSignals(TestCase):
    """Test signals for InvestmentAccountDeposit."""

    def setUp(self):
        """Set up test data."""
        self.account_type = InvestmentAccountType.objects.create(
            name="Test Investment", code="TI"
        )
        self.account = InvestmentAccount.objects.create(
            account_type=self.account_type,
            name="Test Account",
            opening_cash_value=Money(2000, "EUR"),
            opening_date=datetime.date(2023, 1, 1),
        )

    def test_deposit_creates_cash_value_when_enabled(self):
        """Test that a deposit creates a cash value when update_account_cash is True."""
        deposit = InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(800, "EUR"),
            deposit_date=datetime.date(2023, 2, 1),
            update_account_cash=True,
        )

        # Check that an InvestmentAccountCash was created
        cash_value = InvestmentAccountCash.objects.filter(
            account=self.account, value_date=deposit.deposit_date
        ).first()

        assert cash_value is not None
        assert cash_value.value == Money(2800, "EUR")  # 2000 + 800

    def test_deposit_does_not_create_cash_value_when_disabled(self):
        """Test that a deposit doesn't create a cash value when update_account_cash is False."""
        InvestmentAccountDeposit.objects.create(
            account=self.account,
            amount=Money(800, "EUR"),
            deposit_date=datetime.date(2023, 2, 1),
            update_account_cash=False,
        )

        # Check that no InvestmentAccountCash was created for this date
        cash_value = InvestmentAccountCash.objects.filter(
            account=self.account, value_date=datetime.date(2023, 2, 1)
        ).first()

        assert cash_value is None


class TestInvestmentAccountHoldingHistorySignals(TestCase):
    """Test signals for InvestmentAccountHoldingHistory."""

    def setUp(self):
        """Set up test data."""
        self.account_type = InvestmentAccountType.objects.create(
            name="Test Investment", code="TI"
        )
        self.account = InvestmentAccount.objects.create(
            account_type=self.account_type,
            name="Test Account",
            opening_cash_value=Money(5000, "EUR"),
            opening_date=datetime.date(2023, 1, 1),
        )
        self.holding = InvestmentAccountHolding.objects.create(
            account=self.account,
            name="Test Stock",
            code="TST",
            initial_value=Money(100, "EUR"),
            initial_quantity=Decimal("10"),
        )

        # Create initial cash value
        InvestmentAccountCash.objects.create(
            account=self.account,
            value=Money(5000, "EUR"),
            value_date=datetime.date(2023, 1, 1),
        )

    def test_holding_history_subtracts_from_cash_when_cash_used_specified(self):
        """Test that holding history subtracts specified cash amount when cash_used is provided."""
        InvestmentAccountHoldingHistory.objects.create(
            holding=self.holding,
            value=Money(120, "EUR"),
            quantity=Decimal("5"),
            valuation_date=datetime.datetime(2023, 2, 1, 10, 0),
            cash_used=Money(500, "EUR"),  # Specify exact amount to subtract
        )

        # Check that cash was reduced by the specified amount (500 EUR)
        cash_value = InvestmentAccountCash.objects.filter(
            account=self.account, value_date=datetime.date(2023, 2, 1)
        ).first()

        assert cash_value is not None
        assert cash_value.value == Money(4500, "EUR")  # 5000 - 500

    def test_holding_history_does_not_subtract_from_cash_when_no_cash_used(self):
        """Test that holding history doesn't subtract from cash when cash_used is None."""
        InvestmentAccountHoldingHistory.objects.create(
            holding=self.holding,
            value=Money(120, "EUR"),
            quantity=Decimal("5"),
            valuation_date=datetime.datetime(2023, 2, 1, 10, 0),
            cash_used=None,  # No cash specified
        )

        # Check that no new cash value was created for this date
        cash_value = InvestmentAccountCash.objects.filter(
            account=self.account, value_date=datetime.date(2023, 2, 1)
        ).first()

        assert cash_value is None

    def test_holding_history_with_zero_cash_used(self):
        """Test that holding history doesn't subtract when cash_used is zero."""
        InvestmentAccountHoldingHistory.objects.create(
            holding=self.holding,
            value=Money(120, "EUR"),
            quantity=Decimal("5"),
            valuation_date=datetime.datetime(2023, 2, 1, 10, 0),
            cash_used=Money(0, "EUR"),  # Zero cash used
        )

        # Check that no new cash value was created for this date
        cash_value = InvestmentAccountCash.objects.filter(
            account=self.account, value_date=datetime.date(2023, 2, 1)
        ).first()

        assert cash_value is None
