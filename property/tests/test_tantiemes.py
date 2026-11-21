"""Tests of the coproperty tantièmes of a property."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from moneyed import Money

from property.forms import PropertyEditForm
from property.models import Property


def _property(**fields) -> Property:
    return Property(
        name="Flat",
        property_type=Property.APARTMENT,
        buying_value=Money(100_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        **fields,
    )


def test_shares_in_percent():
    prop = _property(
        voting_tantiemes=250,
        voting_tantiemes_total=10_000,
        charges_tantiemes=300,
        charges_tantiemes_total=1_000,
    )
    assert prop.voting_share == Decimal("2.5")
    assert prop.charges_share == Decimal(30)


def test_shares_missing():
    prop = _property(voting_tantiemes=250)
    assert prop.voting_share is None
    assert prop.charges_share is None


def test_clean_accepts_complete_pairs():
    _property(voting_tantiemes=250, voting_tantiemes_total=1000).clean()
    _property().clean()


@pytest.mark.parametrize(
    ("fields", "field_in_error"),
    [
        ({"voting_tantiemes": 250}, "voting_tantiemes_total"),
        (
            {"voting_tantiemes": 250, "voting_tantiemes_total": 0},
            "voting_tantiemes_total",
        ),
        ({"charges_tantiemes_total": 1000}, "charges_tantiemes"),
        (
            {"charges_tantiemes": 1200, "charges_tantiemes_total": 1000},
            "charges_tantiemes",
        ),
    ],
)
def test_clean_rejects_incomplete_or_exceeding_pairs(fields, field_in_error):
    with pytest.raises(ValidationError) as error:
        _property(**fields).clean()
    assert field_in_error in error.value.message_dict


@pytest.mark.django_db
def test_form_has_the_tantiemes_fields():
    fields = PropertyEditForm().fields
    for name in (
        "voting_tantiemes",
        "voting_tantiemes_total",
        "charges_tantiemes",
        "charges_tantiemes_total",
    ):
        assert name in fields
    assert "shares_count" not in fields


@pytest.mark.django_db
def test_detail_shows_the_tantiemes(user_client):
    prop = _property(
        voting_tantiemes=250,
        voting_tantiemes_total=10_000,
        charges_tantiemes=300,
        charges_tantiemes_total=1_000,
    )
    prop.save()
    response = user_client.get(reverse("property:panel_info", args=[prop.pk]))
    content = response.content.decode()
    assert "250 / 10000 (2.50 %)" in content
    assert "300 / 1000 (30 %)" in content


@pytest.mark.django_db
def test_detail_without_tantiemes(user_client):
    prop = _property()
    prop.save()
    response = user_client.get(reverse("property:panel_info", args=[prop.pk]))
    assert "Votes:" not in response.content.decode()
