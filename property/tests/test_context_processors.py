"""Tests for property context processors."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from property.context_processors import nav_properties


@pytest.mark.django_db
def test_nav_properties_unauthenticated():
    """Anonymous user should receive an empty nav_properties list."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = AnonymousUser()

    result = nav_properties(request)

    assert result["nav_properties"] == []
    assert result["nav_properties_any"] is False


@pytest.mark.django_db
def test_nav_properties_authenticated_returns_favorites_only(user, make_property):
    """Authenticated user should receive only active + favorite properties."""
    make_property("Favorite Property", is_active=True, is_favorite=True)
    make_property("Active Non-Favorite", is_active=True, is_favorite=False)
    make_property("Inactive Property", is_active=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert "nav_properties" in result
    props = list(result["nav_properties"])
    assert len(props) == 1
    assert props[0].name == "Favorite Property"


@pytest.mark.django_db
def test_nav_properties_no_active_properties(user, make_property):
    """Authenticated user with no active properties should receive an empty queryset."""
    make_property("Closed Property", is_active=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert "nav_properties" in result
    assert list(result["nav_properties"]) == []
    assert result["nav_properties_any"] is False


@pytest.mark.django_db
def test_nav_properties_ordered_by_name(user, make_property):
    """Favorite properties should be returned ordered alphabetically by name."""
    make_property("Zeta House", is_active=True, is_favorite=True)
    make_property("Alpha House", is_active=True, is_favorite=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    names = [p.name for p in result["nav_properties"]]
    assert names == ["Alpha House", "Zeta House"]
