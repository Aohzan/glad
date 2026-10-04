"""Tests for base view helper functions."""

import datetime
import json
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import RequestFactory
from django.urls import reverse

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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"]
)
def test_apple_touch_icon_redirects_to_the_static_file_without_login(client, path):
    """iOS looks the home screen icon up at the root: point it to the static file."""
    response = client.get(path)
    assert response.status_code == 301
    assert response["Location"] == staticfiles_storage.url("icons/apple-touch-icon.png")


@pytest.mark.django_db
def test_pages_link_the_apple_touch_icon(client):
    """Pages reachable before login link the home screen icon for iOS."""
    response = client.get(reverse("login"))
    assert (
        f'<link rel="apple-touch-icon" href="{staticfiles_storage.url("icons/apple-touch-icon.png")}">'
        in response.content.decode()
    )


def test_manifest_icons_exist_and_cover_any_and_maskable():
    """Every icon of the web app manifest is a static file, both purposes provided."""
    manifest_path = finders.find("manifest.json")
    assert isinstance(manifest_path, str)
    manifest = json.loads(Path(manifest_path).read_text())
    purposes = {icon["purpose"] for icon in manifest["icons"]}
    assert purposes == {"any", "maskable"}
    for icon in manifest["icons"]:
        assert finders.find(icon["src"]), icon["src"]
