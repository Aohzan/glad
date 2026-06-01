"""Tests for format_money template filter."""

import pytest
from moneyed import Money

from base.templatetags.format_money import format_money_filter


def test_format_money_filter_empty_values():
    assert format_money_filter(None) == ""
    assert format_money_filter("") == ""


def test_format_money_filter_invalid_value_type():
    with pytest.raises(ValueError):
        format_money_filter("10")


def test_format_money_filter_with_explicit_locale():
    formatted = format_money_filter(Money(1234.56, "EUR"), locale="en")
    assert formatted
