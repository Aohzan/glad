"""Signals for finance models."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from moneyed import Money

from .models.base import set_day_value
from .models.investment_account import (
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHoldingHistory,
)
from .models.saving_account import SavingAccountDeposit, SavingAccountValue


def _make_deposit_value_handler(
    value_model, update_flag_field, get_current_value, value_date_field="deposit_date"
):
    """Factory: return a post_save handler that records the value after a deposit.

    The value record of the deposit day is created, or replaced when it exists.

    Args:
        value_model: ORM model to create (e.g. SavingAccountValue).
        update_flag_field: Name of the boolean field on the deposit that gates the creation.
        get_current_value: Callable(instance) -> Money returning the current value before deposit.
        value_date_field: Field name on the deposit that holds the date for the new record.
    """

    def handler(sender, instance, created, raw=False, **kwargs):
        # A fixture already holds the values that the deposit made.
        if raw or not (created and getattr(instance, update_flag_field)):
            return
        deposit_date = getattr(instance, value_date_field)
        current = get_current_value(instance, deposit_date)
        new_value = Money(
            current.amount + instance.amount.amount, instance.account.currency
        )
        set_day_value(value_model, "account", instance.account, deposit_date, new_value)

    return handler


def _saving_current_value(instance, deposit_date):
    return instance.account.get_value(max_date=deposit_date)


def _investment_current_cash(instance, deposit_date):
    return instance.account.get_cash_value(max_date=deposit_date)


create_saving_account_value_on_deposit = receiver(
    post_save, sender=SavingAccountDeposit
)(
    _make_deposit_value_handler(
        value_model=SavingAccountValue,
        update_flag_field="update_account_value",
        get_current_value=_saving_current_value,
    )
)

create_investment_account_cash_on_deposit = receiver(
    post_save, sender=InvestmentAccountDeposit
)(
    _make_deposit_value_handler(
        value_model=InvestmentAccountCash,
        update_flag_field="update_account_cash",
        get_current_value=_investment_current_cash,
    )
)


@receiver(post_save, sender=InvestmentAccountHoldingHistory)
def subtract_cash_on_holding_transaction(
    sender, instance, created, raw=False, **kwargs
):
    """Subtract the specified cash amount from account cash when cash_used is provided."""
    if created and not raw and instance.cash_used:
        instance.holding.account.subtract_cash(
            amount=instance.cash_used,
            at_date=instance.valuation_date,
        )
