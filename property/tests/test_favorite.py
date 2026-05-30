"""Tests for property favorite toggle functionality."""

import datetime

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse
from moneyed import Money

from property.context_processors import nav_properties
from property.models import Property


def _make_property(name, is_active=True, is_favorite=False):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=is_active,
        is_favorite=is_favorite,
    )


# ─── Context processor ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_nav_properties_unauthenticated_returns_empty():
    """Anonymous user should receive empty nav_properties."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = AnonymousUser()

    result = nav_properties(request)

    assert result["nav_properties"] == []
    assert result["nav_properties_any"] is False


@pytest.mark.django_db
def test_nav_properties_shows_only_favorites(user):
    """Only active + favorite properties should appear in nav."""
    _make_property("Favorite", is_favorite=True)
    _make_property("Not Favorite", is_favorite=False)
    _make_property("Inactive Favorite", is_active=False, is_favorite=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    names = [p.name for p in result["nav_properties"]]
    assert names == ["Favorite"]


@pytest.mark.django_db
def test_nav_properties_any_true_when_active_exist(user):
    """nav_properties_any should be True when active properties exist."""
    _make_property("Active", is_favorite=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert result["nav_properties_any"] is True
    assert result["nav_properties"] == []


@pytest.mark.django_db
def test_nav_properties_any_false_when_no_active(user):
    """nav_properties_any should be False when no active properties exist."""
    _make_property("Inactive", is_active=False, is_favorite=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    assert result["nav_properties_any"] is False


@pytest.mark.django_db
def test_nav_properties_ordered_by_name(user):
    """Favorite properties should be ordered alphabetically."""
    _make_property("Zeta", is_favorite=True)
    _make_property("Alpha", is_favorite=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_properties(request)

    names = [p.name for p in result["nav_properties"]]
    assert names == ["Alpha", "Zeta"]


# ─── Toggle view ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_toggle_favorite_adds_favorite(user_client):
    """POST to toggle_favorite should set is_favorite=True on a non-favorite."""
    prop = _make_property("Test Property", is_favorite=False)

    url = reverse("property:toggle_favorite", kwargs={"pk": prop.pk})
    response = user_client.post(url)

    prop.refresh_from_db()
    assert prop.is_favorite is True
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_favorite_removes_favorite(user_client):
    """POST to toggle_favorite should set is_favorite=False on a favorite."""
    prop = _make_property("Test Property", is_favorite=True)

    url = reverse("property:toggle_favorite", kwargs={"pk": prop.pk})
    response = user_client.post(url)

    prop.refresh_from_db()
    assert prop.is_favorite is False
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_favorite_get_not_allowed(user_client):
    """GET request to toggle_favorite should return 405."""
    prop = _make_property("Test Property")

    url = reverse("property:toggle_favorite", kwargs={"pk": prop.pk})
    response = user_client.get(url)

    assert response.status_code == 405


@pytest.mark.django_db
def test_toggle_favorite_requires_login(client):
    """Unauthenticated POST should redirect to login."""
    prop = _make_property("Test Property")

    url = reverse("property:toggle_favorite", kwargs={"pk": prop.pk})
    response = client.post(url)

    assert response.status_code == 302
    assert "/login/" in response["Location"] or "accounts/login" in response["Location"]


@pytest.mark.django_db
def test_toggle_favorite_404_on_missing(user_client):
    """POST to toggle_favorite with unknown pk should return 404."""
    url = reverse("property:toggle_favorite", kwargs={"pk": 99999})
    response = user_client.post(url)

    assert response.status_code == 404
