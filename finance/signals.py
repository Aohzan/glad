"""Signals for finance models."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from moneyed import Money

from .models.investment_account import (
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHoldingHistory,
)
from .models.saving_account import SavingAccountDeposit, SavingAccountValue


@receiver(post_save, sender=SavingAccountDeposit)
def create_saving_account_value_on_deposit(sender, instance, created, **kwargs):
    """Create a SavingAccountValue when a deposit is made and update_account_value is True."""
    if created and instance.update_account_value:
        # Get current account value
        current_value = instance.account.get_value(max_date=instance.deposit_date)

        # Add deposit amount to current value
        new_value = Money(
            current_value.amount + instance.amount.amount, instance.account.currency
        )

        # Create or update SavingAccountValue for this date
        SavingAccountValue.objects.create(
            account=instance.account, value_date=instance.deposit_date, value=new_value
        )


@receiver(post_save, sender=InvestmentAccountDeposit)
def create_investment_account_cash_on_deposit(sender, instance, created, **kwargs):
    """Create an InvestmentAccountCash when a deposit is made and update_account_cash is True."""
    if created and instance.update_account_cash:
        # Get current cash value
        current_cash_value = instance.account.get_cash_value(
            max_date=instance.deposit_date
        )

        # Add deposit amount to current cash value
        new_cash_value = Money(
            current_cash_value.amount + instance.amount.amount,
            instance.account.currency,
        )

        # Create or update InvestmentAccountCash for this date
        InvestmentAccountCash.objects.create(
            account=instance.account,
            value_date=instance.deposit_date,
            value=new_cash_value,
        )


@receiver(post_save, sender=InvestmentAccountHoldingHistory)
def subtract_cash_on_holding_transaction(sender, instance, created, **kwargs):
    """Subtract the specified cash amount from account cash when cash_used is provided."""
    if created and instance.cash_used:
        # Get current cash value
        current_cash_value = instance.holding.account.get_cash_value(
            max_date=instance.valuation_date
        )

        # Subtract the specified cash amount from current cash value
        new_cash_value = Money(
            current_cash_value.amount - instance.cash_used.amount,
            instance.holding.account.currency,
        )

        # Convert datetime to date for InvestmentAccountCash
        cash_date = (
            instance.valuation_date.date()
            if hasattr(instance.valuation_date, "date")
            else instance.valuation_date
        )

        # Create or update InvestmentAccountCash for this date
        InvestmentAccountCash.objects.create(
            account=instance.holding.account, value_date=cash_date, value=new_cash_value
        )
