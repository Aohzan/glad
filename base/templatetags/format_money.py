from moneyed import Money
from moneyed.l10n import format_money
from django import template
from django.utils import translation

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
