"""Test base views."""

import datetime

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Property
from property.models.scpi import SCPI
from tests.conftest import ADMIN_USER


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("index")
    response = client.get(path)
    assert response.url == "/accounts/login/?next=/"
    assert response.status_code == 302


@pytest.mark.django_db
def test_index_view_authenticated(admin_client):
    """Test that authenticated users can access the index page."""
    response = admin_client.get(reverse("index"))
    assert response.status_code == 200
    assert ADMIN_USER in response.content.decode()


@pytest.mark.django_db
def test_index_view_context_has_property_pks(admin_client):
    """Index view context contains only the list of active property PKs."""
    prop = Property.objects.create(
        name="My Flat",
        buying_date=datetime.date(2022, 1, 1),
        buying_value=Money(200000, "EUR"),
        is_active=True,
    )
    inactive = Property.objects.create(
        name="Old House",
        buying_date=datetime.date(2010, 1, 1),
        buying_value=Money(100000, "EUR"),
        is_active=False,
    )
    response = admin_client.get(reverse("index"))
    assert response.status_code == 200
    pks = response.context["property_pks"]
    assert prop.pk in pks
    assert inactive.pk not in pks


@pytest.mark.django_db
def test_index_view_no_properties(admin_client):
    """Index view context has empty list when no active properties."""
    response = admin_client.get(reverse("index"))
    assert response.status_code == 200
    assert response.context["property_pks"] == []
    assert response.context["scpi_pks"] == []


@pytest.mark.django_db
def test_index_view_context_has_scpi_pks(admin_client):
    """Index view context contains SCPI PKs ordered by name."""
    scpi = SCPI.objects.create(name="Corum Eurion")
    response = admin_client.get(reverse("index"))
    assert response.status_code == 200
    assert scpi.pk in response.context["scpi_pks"]


def test_error_400(client):
    """Test the 400 error page renders correctly."""
    from base.views import error_400

    request = client.get("/").wsgi_request
    response = error_400(request)
    assert response.status_code == 400
    assert b"400" in response.content


def test_error_403(client):
    """Test the 403 error page renders correctly."""
    from base.views import error_403

    request = client.get("/").wsgi_request
    response = error_403(request)
    assert response.status_code == 403
    assert b"403" in response.content


def test_error_404(client):
    """Test the 404 error page renders correctly."""
    from base.views import error_404

    request = client.get("/").wsgi_request
    response = error_404(request)
    assert response.status_code == 404
    assert b"404" in response.content


def test_error_500(client):
    """Test the 500 error page renders correctly."""
    from base.views import error_500

    request = client.get("/").wsgi_request
    response = error_500(request)
    assert response.status_code == 500
    assert b"500" in response.content
