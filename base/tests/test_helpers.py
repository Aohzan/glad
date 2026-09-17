"""Tests for base view helper functions."""

import datetime

import pytest
from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import RequestFactory

from base.views import healthcheck, safe_date_compare


def test_safe_date_compare_handles_mixed_date_types():
    date_value = datetime.date(2025, 1, 2)
    dt_value = datetime.datetime(2025, 1, 3, 10, 0, 0)

    assert safe_date_compare(date_value, dt_value) is True
    assert safe_date_compare(dt_value, date_value) is False
    assert safe_date_compare(date_value, date_value) is True


def test_healthcheck_view_returns_ok_json():
    request = RequestFactory().get("/health")
    response = healthcheck(request)
    assert response.status_code == 200
    assert response.content.decode("utf-8") == '{"status": "OK"}'


@pytest.mark.django_db
def test_healthcheck_is_reachable_without_login(client):
    """The health endpoint must not redirect to the login page."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


@pytest.mark.django_db
def test_csp_header_and_nonce_on_rendered_pages(user_client):
    """Pages send a CSP header and inline scripts carry the matching nonce."""
    response = user_client.get("/")
    assert response.status_code == 200
    csp = response["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in csp
    nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'nonce="{nonce}"' in response.content.decode()
    assert "onclick=" not in response.content.decode()


@pytest.mark.django_db
def test_favicon_redirects_to_the_static_file_without_login(client):
    """Browsers hit /favicon.ico at the root: answer instead of raising a 404."""
    response = client.get("/favicon.ico")
    assert response.status_code == 301
    assert response["Location"] == staticfiles_storage.url("favicon.ico")
