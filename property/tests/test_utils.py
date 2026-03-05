"""Tests for property utility classes."""

from decimal import Decimal
from typing import cast

import pytest
from moneyed import Money

from property.models import Property
from property.utils import PropertyProgression, PropertyRentability


def test_property_progression_positive_case():
    progression = PropertyProgression(
        current_value=Money(120000, "EUR"),
        old_value=Money(100000, "EUR"),
    )
    assert progression.progression == 20
    assert progression.css_class == "text-success"
    assert str(progression) == "20% (20000.0)"


def test_property_progression_negative_case():
    progression = PropertyProgression(
        current_value=Money(90000, "EUR"),
        old_value=Money(100000, "EUR"),
    )
    assert progression.progression == -10
    assert progression.css_class == "text-danger"


def test_property_progression_zero_old_value_case():
    progression = PropertyProgression(
        current_value=Money(0, "EUR"),
        old_value=Money(0, "EUR"),
    )
    assert progression.progression == 0
    assert progression.css_class == "text-muted"


def test_property_rentability_not_implemented():
    with pytest.raises(NotImplementedError):
        PropertyRentability(property=cast(Property, object()))


def test_property_rentability_str_representation_without_init():
    rentability = PropertyRentability.__new__(PropertyRentability)
    rentability.rentability_percent = Decimal(5)
    assert str(rentability) == "5%"
