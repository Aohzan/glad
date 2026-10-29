"""Tests for the notification inbox and settings pages."""

import pytest
from django.urls import reverse

from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
)


def _notification(user, **kwargs):
    defaults = {"type_key": "sample", "dedup_key": kwargs.get("title", "t")}
    return Notification.objects.create(user=user, **{**defaults, **kwargs})


def _channel(user, name="Phone"):
    channel = NotificationChannel(user=user, name=name)
    channel.url = "ntfy://ntfy.sh/secret-topic"
    channel.save()
    return channel


@pytest.mark.django_db
def test_bell_shows_the_unread_count(user_client, user):
    Notification.objects.filter(type_key="login").delete()
    _notification(user, title="One")
    _notification(user, title="Two", read_at="2026-10-01 10:00")
    response = user_client.get(reverse("index"))
    content = response.content.decode()
    assert 'class="g-bell__count">1<' in content
    assert reverse("notifications:dropdown") in content


@pytest.mark.django_db
def test_bell_caps_the_count(user_client, user):
    for index in range(100):
        _notification(user, title=f"N{index}")
    response = user_client.get(reverse("index"))
    assert 'class="g-bell__count">99+<' in response.content.decode()


@pytest.mark.django_db
def test_inbox_lists_only_the_user_notifications(user_client, user, admin_user):
    _notification(user, title="Mine", body="Details")
    _notification(admin_user, title="Not mine")
    response = user_client.get(reverse("notifications:inbox"))
    content = response.content.decode()
    assert "Mine" in content
    assert "Details" in content
    assert "Not mine" not in content


@pytest.mark.django_db
def test_inbox_empty(user_client):
    Notification.objects.filter(type_key="login").delete()
    response = user_client.get(reverse("notifications:inbox"))
    assert "No notification yet" in response.content.decode()


@pytest.mark.django_db
def test_dropdown_lists_the_latest(user_client, user):
    for index in range(12):
        _notification(user, title=f"Item {index}")
    response = user_client.get(reverse("notifications:dropdown"))
    assert response.content.decode().count('class="g-notif ') == 10


@pytest.mark.django_db
def test_open_marks_read_and_follows_an_internal_link(user_client, user):
    notification = _notification(user, title="Go", url="/property/checks/")
    response = user_client.get(reverse("notifications:open", args=[notification.pk]))
    assert response.url == "/property/checks/"
    notification.refresh_from_db()
    assert notification.read_at is not None


@pytest.mark.django_db
def test_open_follows_an_https_link(user_client, user):
    notification = _notification(user, title="Go", url="https://www.impots.gouv.fr/")
    response = user_client.get(reverse("notifications:open", args=[notification.pk]))
    assert response.url == "https://www.impots.gouv.fr/"


@pytest.mark.django_db
def test_open_without_a_usable_link_goes_to_the_inbox(user_client, user):
    notification = _notification(user, title="Go", url="javascript:alert(1)")
    response = user_client.get(reverse("notifications:open", args=[notification.pk]))
    assert response.url == reverse("notifications:inbox")


@pytest.mark.django_db
def test_open_someone_else_notification(user_client, admin_user):
    notification = _notification(admin_user, title="Private")
    response = user_client.get(reverse("notifications:open", args=[notification.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_mark_all_read(user_client, user, admin_user):
    _notification(user, title="A")
    other = _notification(admin_user, title="B")
    user_client.post(reverse("notifications:mark_all_read"))
    assert not Notification.objects.filter(user=user, read_at__isnull=True).exists()
    other.refresh_from_db()
    assert other.read_at is None


@pytest.mark.django_db
def test_settings_page_lists_types_and_hides_the_url(user_client, user):
    _channel(user)
    _channel(user, "Mail")
    response = user_client.get(reverse("notifications:settings"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "secret-topic" not in content
    assert "ntfy://…" in content
    assert 'name="stale_data-days"' in content
    assert 'name="lmnp_return-deadline"' in content
    assert 'name="stale_data-channels"' in content
    # Every type is enabled by default, without a stored preference.
    assert 'name="app_release-enabled" id="app_release-enabled" checked' in content
    assert 'name="stale_data-enabled" id="stale_data-enabled" checked' in content


@pytest.mark.django_db
def test_save_preferences(user_client, user, admin_user):
    phone = _channel(user)
    foreign = _channel(admin_user, "Foreign")
    response = user_client.post(
        reverse("notifications:settings"),
        {
            "stale_data-enabled": "on",
            "stale_data-days": "45",
            "stale_data-long_days": "365",
            "stale_data-channels": [str(phone.pk), str(foreign.pk), "x"],
            "lmnp_return-deadline": "05-19",
            "lmnp_return-days_before": "30",
            "income_tax_return-opening": "04-10",
            "income_tax_return-deadline": "06-04",
            "income_tax_return-days_before": "14",
            "local_taxes-property_tax": "10-15",
            "local_taxes-cfe": "12-15",
            "local_taxes-days_before": "15",
            **_default_days(),
        },
    )
    assert response.status_code == 302
    pref = NotificationPreference.objects.get(user=user, type_key="stale_data")
    assert pref.enabled
    assert pref.params == {"days": 45, "long_days": 365}
    assert list(pref.channels.all()) == [phone]
    assert not NotificationPreference.objects.get(
        user=user, type_key="app_release"
    ).enabled


def _default_days() -> dict:
    """Valid values for the other numeric and choice settings."""
    from notifications.registry import types

    values = {}
    for notification_type in types():
        for param in notification_type.params:
            if param.kind in ("int", "choice", "monthday"):
                values[f"{notification_type.key}-{param.key}"] = str(param.default)
    values["stale_data-days"] = "45"
    return values


@pytest.mark.django_db
def test_invalid_preferences_are_not_saved(user_client, user):
    response = user_client.post(
        reverse("notifications:settings"),
        {**_default_days(), "stale_data-enabled": "on", "stale_data-days": "0"},
    )
    assert response.status_code == 400
    content = response.content.decode()
    assert "at least 1" in content
    assert 'name="stale_data-enabled" id="stale_data-enabled" checked' in content
    assert not NotificationPreference.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_add_channel(user_client, user):
    response = user_client.post(
        reverse("notifications:add_channel"),
        {"name": "Phone", "url": " ntfy://ntfy.sh/topic "},
    )
    assert response.status_code == 302
    channel = NotificationChannel.objects.get(user=user)
    assert channel.url == "ntfy://ntfy.sh/topic"


@pytest.mark.django_db
def test_add_channel_rejects_an_invalid_url(user_client, user):
    response = user_client.post(
        reverse("notifications:add_channel"),
        {"name": "Phone", "url": "not a url"},
    )
    assert response.status_code == 400
    assert "not a valid Apprise URL" in response.content.decode()
    assert not NotificationChannel.objects.exists()


@pytest.mark.django_db
def test_test_channel(user_client, user, apprise_mock):
    channel = _channel(user)
    response = user_client.post(
        reverse("notifications:test_channel", args=[channel.pk]), follow=True
    )
    assert "Test notification sent" in response.content.decode()
    apprise_mock.notify.return_value = False
    response = user_client.post(
        reverse("notifications:test_channel", args=[channel.pk]), follow=True
    )
    assert "The test notification failed" in response.content.decode()


@pytest.mark.django_db
def test_toggle_and_delete_channel(user_client, user):
    channel = _channel(user)
    user_client.post(reverse("notifications:toggle_channel", args=[channel.pk]))
    channel.refresh_from_db()
    assert not channel.enabled
    user_client.post(reverse("notifications:delete_channel", args=[channel.pk]))
    assert not NotificationChannel.objects.exists()


@pytest.mark.django_db
def test_channels_of_other_users_are_out_of_reach(user_client, admin_user):
    channel = _channel(admin_user)
    for name in ("test_channel", "toggle_channel", "delete_channel"):
        response = user_client.post(reverse(f"notifications:{name}", args=[channel.pk]))
        assert response.status_code == 404
    assert NotificationChannel.objects.filter(pk=channel.pk, enabled=True).exists()


@pytest.mark.django_db
def test_account_settings_link_to_the_notification_settings(user_client):
    response = user_client.get(reverse("accounts:settings"))
    assert reverse("notifications:settings") in response.content.decode()


@pytest.mark.django_db
def test_use_my_email(user_client, user):
    response = user_client.get(reverse("notifications:settings"))
    assert "Use my email" in response.content.decode()
    user_client.post(reverse("notifications:add_email_channel"))
    user_client.post(reverse("notifications:add_email_channel"))
    channel = NotificationChannel.objects.get(user=user)
    assert channel.kind == NotificationChannel.Kind.EMAIL
    response = user_client.get(reverse("notifications:settings"))
    content = response.content.decode()
    assert "Use my email" not in content
    assert "user@site.com" in content


@pytest.mark.django_db
def test_use_my_email_without_an_address(user_client, user):
    user.email = ""
    user.save()
    response = user_client.get(reverse("notifications:settings"))
    assert "Enter an email address in" in response.content.decode()
    response = user_client.post(reverse("notifications:add_email_channel"), follow=True)
    assert "Enter an email address in your settings first." in (
        response.content.decode()
    )
    assert not NotificationChannel.objects.exists()
