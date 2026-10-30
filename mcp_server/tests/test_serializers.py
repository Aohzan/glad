"""Tests of the JSON conversion and of the error messages."""

import dataclasses
import datetime
import enum
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy
from djmoney.money import Money

from mcp_server.models import ApiKey, McpCallLog
from mcp_server.serializers import decimal, money, percent, quantity, ref, to_json
from mcp_server.server import _error_message


class Color(enum.Enum):
    RED = "red"


@dataclasses.dataclass
class Point:
    day: datetime.date
    amount: Decimal

    @property
    def ignored(self) -> int:
        return 1


def test_decimal_rounds_to_the_cent_without_trailing_zeros():
    assert decimal(Decimal("1234.50000")) == "1234.5"
    assert decimal(Decimal(100)) == "100"
    assert decimal(Decimal("687153.817")) == "687153.82"
    assert decimal(Decimal("0.123456"), 4) == "0.1235"
    assert decimal(Decimal("-0.001")) == "0"
    assert decimal(31.823456789) == "31.82"


def test_percent():
    assert percent(None) is None
    assert percent(12.3456) == "12.35"


def test_quantity_keeps_the_fractions_of_units():
    assert quantity(Decimal("102.256000")) == "102.256"
    assert quantity(Decimal("23.9945")) == "23.9945"
    assert quantity(None) is None


def test_money_and_ref_of_none():
    assert money(None) is None
    assert ref(None) is None
    assert money(Money("12.30", "EUR")) == {"amount": "12.3", "currency": "EUR"}


def test_to_json_converts_nested_values():
    value = {
        1: [Point(datetime.date(2026, 1, 2), Decimal("3.50"))],
        "color": Color.RED,
        "label": gettext_lazy("Name"),
        "when": datetime.datetime(2026, 1, 2, 3, 4),
        "set": {True},
        "ratio": 0.0534567,
        "other": object,
    }
    assert to_json(value) == {
        "1": [{"day": "2026-01-02", "amount": "3.5"}],
        "color": "red",
        "label": "Name",
        "when": "2026-01-02",
        "set": [True],
        "ratio": "0.0535",
        "other": str(object),
    }


@pytest.mark.django_db
def test_to_json_of_a_model_is_a_reference(user):
    key, _raw = ApiKey.create(user, "Laptop")
    log = McpCallLog.objects.create(api_key=key, tool="get_net_worth")
    assert to_json(key) == {"id": key.pk, "label": "Laptop"}
    assert str(log) == "get_net_worth"


def test_error_message_of_a_validation_error():
    assert _error_message(ValidationError("Too big.")) == "Too big."
    assert _error_message(ValidationError({"amount": ["Too big."]})) == (
        '{"amount": ["Too big."]}'
    )
