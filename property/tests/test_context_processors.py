"""Tests for property context processors."""

import datetime

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from moneyed import Money

from property.context_processors import nav_properties
from property.models import Property


def _make_property(name, is_active):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=is_active,
    )


@pytest.mark.django_db
def test_nav_properties_unauthenticated():
    """Anonymous user should receive an empty nav_properties list."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = AnonymousUser()

    result = nav_properties(request)

    assert result == {"nav_properties": []}


@pytest.mark.django_db
def test_nav_properties_authenticated_returns_active_only(user):
    """Authenticated user should receive only active properties."""
    _make_property("Active Property", is_active=True)
    _make_property("Inactive Property", is_active=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert "nav_properties" in result
    props = list(result["nav_properties"])
    assert len(props) == 1
    assert props[0].name == "Active Property"


@pytest.mark.django_db
def test_nav_properties_no_active_properties(user):
    """Authenticated user with no active properties should receive an empty queryset."""
    _make_property("Closed Property", is_active=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert "nav_properties" in result
    assert list(result["nav_properties"]) == []


@pytest.mark.django_db
def test_nav_properties_ordered_by_name(user):
    """Active properties should be returned ordered alphabetically by name."""
    _make_property("Zeta House", is_active=True)
    _make_property("Alpha House", is_active=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    names = [p.name for p in result["nav_properties"]]
    assert names == ["Alpha House", "Zeta House"]
