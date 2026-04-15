from decimal import Decimal

from django import template
from django.utils import translation
from moneyed import Money
from moneyed.l10n import format_money

register = template.Library()


@register.filter(name="format_money")
def format_money_filter(money: Money | str | None, locale: str | None = None):
    """Format a Money instance according to the given locale."""
    if money is None or money == "":
        return ""
    if not isinstance(money, Money):
        raise ValueError("The provided value is not a Money instance.")
    if locale is None:
        locale = translation.get_language()
    return format_money(money, locale=locale)


@register.filter(name="format_money_amount")
def format_money_amount_filter(
    amount: Decimal | int | float | None, currency: str = "EUR"
):
    """Format a raw Decimal/numeric amount as money using the given currency code.

    Usage: {{ some_decimal|format_money_amount:property.currency }}
    """
    if amount is None:
        return ""
    locale = translation.get_language()
    money = Money(amount, currency)
    return format_money(money, locale=locale)
