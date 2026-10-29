"""Tests of the MCP access settings page."""

import pytest
from django.urls import reverse

from mcp_server.models import ApiKey, McpCallLog


@pytest.mark.django_db
def test_settings_lists_only_the_user_keys_and_calls(
    user_client, user, admin_user, settings
):
    settings.APP_URL = ""
    mine, _raw = ApiKey.create(user, "Mine", can_write=True)
    other, _raw = ApiKey.create(admin_user, "Not mine")
    McpCallLog.objects.create(
        api_key=mine, tool="get_net_worth", arguments={"currency": "EUR"}
    )
    McpCallLog.objects.create(
        api_key=mine,
        tool="add_ledger_entry",
        is_write=True,
        success=False,
        error="Bad amount",
    )
    McpCallLog.objects.create(api_key=other, tool="secret_tool")
    content = user_client.get(reverse("mcp_server:settings")).content.decode()
    assert "Mine" in content
    assert f"glad_{mine.prefix}_" in content
    assert "Read and write" in content
    assert "Not mine" not in content
    assert "get_net_worth" in content
    assert "currency=EUR" in content
    assert "Bad amount" in content
    assert "secret_tool" not in content
    assert "http://testserver/mcp" in content


@pytest.mark.django_db
def test_settings_page_is_linked_from_the_account_settings(user_client):
    content = user_client.get(reverse("accounts:settings")).content.decode()
    assert reverse("mcp_server:settings") in content


@pytest.mark.django_db
def test_settings_uses_app_url(user_client, settings):
    settings.APP_URL = "https://glad.example.com"
    content = user_client.get(reverse("mcp_server:settings")).content.decode()
    assert "https://glad.example.com/mcp" in content


@pytest.mark.django_db
def test_add_key_shows_it_once(user_client, user):
    response = user_client.post(
        reverse("mcp_server:add_key"), {"name": "Laptop", "can_write": "on"}
    )
    assert response.status_code == 302
    key = ApiKey.objects.get(user=user)
    assert key.name == "Laptop"
    assert key.can_write
    first = user_client.get(reverse("mcp_server:settings")).content.decode()
    assert f"Bearer glad_{key.prefix}_" in first
    raw = first.split("Bearer ")[1].split('"')[0]
    assert ApiKey.lookup(raw) == key
    second = user_client.get(reverse("mcp_server:settings")).content.decode()
    assert "Bearer glad_" not in second


@pytest.mark.django_db
def test_add_key_read_only_by_default(user_client, user):
    user_client.post(reverse("mcp_server:add_key"), {"name": "Reader"})
    assert not ApiKey.objects.get(user=user).can_write


@pytest.mark.django_db
def test_add_key_invalid(user_client, user):
    response = user_client.post(reverse("mcp_server:add_key"), {"name": ""})
    assert response.status_code == 400
    assert not ApiKey.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_toggle_key(user_client, user):
    key, _raw = ApiKey.create(user, "Laptop")
    user_client.post(reverse("mcp_server:toggle_key", args=[key.pk]))
    key.refresh_from_db()
    assert not key.is_active
    content = user_client.get(reverse("mcp_server:settings")).content.decode()
    assert "Disabled" in content
    user_client.post(reverse("mcp_server:toggle_key", args=[key.pk]))
    key.refresh_from_db()
    assert key.is_active


@pytest.mark.django_db
def test_delete_key(user_client, user):
    key, _raw = ApiKey.create(user, "Laptop")
    response = user_client.post(reverse("mcp_server:delete_key", args=[key.pk]))
    assert response.status_code == 302
    assert not ApiKey.objects.filter(pk=key.pk).exists()


@pytest.mark.django_db
def test_cannot_touch_the_key_of_another_user(user_client, admin_user):
    key, _raw = ApiKey.create(admin_user, "Admin")
    assert (
        user_client.post(reverse("mcp_server:toggle_key", args=[key.pk])).status_code
        == 404
    )
    assert (
        user_client.post(reverse("mcp_server:delete_key", args=[key.pk])).status_code
        == 404
    )
    assert ApiKey.objects.get(pk=key.pk).is_active


@pytest.mark.django_db
def test_views_require_post(user_client, user):
    key, _raw = ApiKey.create(user, "Laptop")
    assert (
        user_client.get(reverse("mcp_server:delete_key", args=[key.pk])).status_code
        == 405
    )


@pytest.mark.django_db
def test_settings_requires_login(client):
    response = client.get(reverse("mcp_server:settings"))
    assert response.status_code == 302
