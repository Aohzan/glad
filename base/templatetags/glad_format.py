"""Locale-aware number filters for the dashboard figures.

``money0`` rounds to whole units (``24 100 €``), ``signed_money0`` and ``pct``
always show the sign (``+2,56 %``, ``−500 €``) and ``tone`` returns the CSS
class colouring a value by its sign.
"""

from decimal import Decimal, InvalidOperation

from babel import Locale, UnknownLocaleError
from babel.numbers import format_currency, format_percent
from django import template
from django.conf import settings
from django.utils import translation

register = template.Library()

MINUS = "−"


def _locale() -> Locale:
    try:
        return Locale.parse(translation.to_locale(translation.get_language() or "en"))
    except UnknownLocaleError, ValueError:
        return Locale.parse("en")


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(getattr(value, "amount", value)))
    except InvalidOperation, ValueError:
        return None


def _with_digits(pattern: str, digits: int) -> str:
    """*pattern* with exactly *digits* fraction digits."""
    integer = pattern.split(";")[0]
    if "." in integer:
        head, tail = integer.split(".", 1)
        tail = tail.lstrip("0#")
        integer = head + tail
    if digits:
        cut = integer.rfind("0") + 1
        integer = integer[:cut] + "." + "0" * digits + integer[cut:]
    return integer


def _money(amount: Decimal, currency) -> str:
    currency = str(currency or "") or settings.DEFAULT_CURRENCY
    locale = _locale()
    pattern = _with_digits(locale.currency_formats["standard"].pattern, 0)
    return format_currency(
        amount.quantize(Decimal(1)),
        currency,
        format=pattern,
        locale=locale,
        currency_digits=False,
    )


@register.filter
def money0(value, currency: str = "EUR") -> str:
    """Amount rounded to whole units with its currency symbol."""
    amount = _decimal(value)
    if amount is None:
        return ""
    currency = str(getattr(getattr(value, "currency", None), "code", currency))
    return _money(amount, currency).replace("-", MINUS)


@register.filter
def signed_money0(value, currency: str = "EUR") -> str:
    """Like ``money0`` with an explicit ``+`` or ``−`` sign."""
    amount = _decimal(value)
    if amount is None:
        return ""
    currency = str(getattr(getattr(value, "currency", None), "code", currency))
    rounded = amount.quantize(Decimal(1))
    text = _money(abs(rounded), currency)
    if rounded > 0:
        return "+" + text
    if rounded < 0:
        return MINUS + text
    return text


@register.filter
def pct(value, digits: int = 2) -> str:
    """Signed percentage, ``—`` when unknown."""
    number = _decimal(value)
    if number is None:
        return "—"
    locale = _locale()
    pattern = _with_digits(locale.percent_formats[None].pattern, int(digits))
    text = format_percent(abs(number) / 100, format=pattern, locale=locale)
    rounded = round(number, int(digits))
    if rounded > 0:
        return "+" + text
    if rounded < 0:
        return MINUS + text
    return text


@register.filter
def share(value, digits: int = 1) -> str:
    """Unsigned percentage (a weight or a ratio)."""
    number = _decimal(value)
    if number is None:
        return "—"
    locale = _locale()
    pattern = _with_digits(locale.percent_formats[None].pattern, int(digits))
    return format_percent(number / 100, format=pattern, locale=locale)


@register.filter
def tone(value) -> str:
    """``g-pos`` for a positive value, ``g-neg`` for a negative one."""
    number = _decimal(value)
    if not number:
        return ""
    return "g-pos" if number > 0 else "g-neg"


@register.filter
def css_pct(value, minimum: float = 0) -> str:
    """Percentage for a CSS width, clamped to [minimum, 100] with a dot decimal."""
    number = _decimal(value)
    if number is None:
        number = Decimal(0)
    clamped = max(Decimal(str(minimum)), min(Decimal(100), number))
    return f"{clamped:.2f}%"


@register.filter
def percent_of(value, total) -> Decimal | None:
    """*value* as a percentage of *total*, None when *total* is zero."""
    number, base = _decimal(value), _decimal(total)
    if number is None or not base:
        return None
    return number / base * 100
