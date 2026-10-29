"""Tests for running the checks and delivering the notifications."""

import datetime
from typing import cast
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import UserManager

from base.models import SentEmail
from base.scheduler import Job, job_failed
from base.services.mailer import email_failed
from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
)
from notifications.registry import Event
from notifications.services import (
    deliver,
    format_message,
    household_users,
    notify,
    run_checks,
    send_to_channel,
    subscriptions,
    unread_count,
)
from notifications.tests.conftest import CHECK_CALLS, TODAY, broken_check

User = get_user_model()


def _channel(user, name="Phone", url="ntfy://ntfy.sh/topic"):
    channel = NotificationChannel(user=user, name=name)
    channel.url = url
    channel.save()
    return channel


def _only_user(user):
    """Deactivate every other household member, so only *user* is notified."""
    User.objects.exclude(pk=user.pk).update(is_active=False)


@pytest.mark.django_db
def test_household_users_exclude_children_and_inactive(user):
    users_manager = cast(UserManager, User.objects)
    child = users_manager.create_user("kid")
    child.profile.is_child = True
    child.profile.save()
    inactive = users_manager.create_user("gone", is_active=False)
    users = list(household_users())
    assert user in users
    assert child not in users
    assert inactive not in users


@pytest.mark.django_db
def test_subscriptions_use_preferences_then_defaults(user, sample_types):
    _only_user(user)
    assert subscriptions(sample_types["sample"]) == []
    assert [s.user for s in subscriptions(sample_types["periodic"])] == [user]
    channel = _channel(user)
    pref = NotificationPreference.objects.create(
        user=user, type_key="sample", enabled=True, params={"threshold": 9}
    )
    pref.channels.add(channel)
    (subscription,) = subscriptions(sample_types["sample"])
    assert subscription.params == {"threshold": 9}
    assert subscription.channel_ids == [channel.pk]
    NotificationPreference.objects.create(user=user, type_key="periodic", enabled=False)
    assert subscriptions(sample_types["periodic"]) == []


@pytest.mark.django_db
def test_run_checks_records_each_event_once(user, sample_types, apprise_mock):
    _only_user(user)
    NotificationPreference.objects.create(user=user, type_key="sample", enabled=True)
    assert run_checks(TODAY) == "3 notification(s)"
    assert run_checks(TODAY) == "0 notification(s)"
    titles = set(Notification.objects.filter(user=user).values_list("title", flat=True))
    assert titles == {"Alert A 5", "Alert B", "Periodic"}
    assert unread_count(user) == 3


@pytest.mark.django_db
def test_run_checks_once_per_distinct_settings(user, admin_user, sample_types):
    User.objects.exclude(pk__in=[user.pk, admin_user.pk]).update(is_active=False)
    NotificationPreference.objects.create(user=user, type_key="sample", enabled=True)
    NotificationPreference.objects.create(
        user=admin_user, type_key="sample", enabled=True, params={"threshold": 5}
    )
    run_checks(TODAY)
    assert CHECK_CALLS == [{"threshold": 5}]


@pytest.mark.django_db
def test_renotified_events_wait_for_their_delay(user, sample_types):
    _only_user(user)
    run_checks(TODAY)
    run_checks(TODAY + datetime.timedelta(days=6))
    assert Notification.objects.filter(type_key="periodic").count() == 1
    run_checks(TODAY + datetime.timedelta(days=7))
    assert Notification.objects.filter(type_key="periodic").count() == 2


@pytest.mark.django_db
def test_a_failing_check_does_not_stop_the_others(user, sample_types):
    _only_user(user)
    from notifications import registry
    from notifications.registry import NotificationType

    registry.register(
        NotificationType(
            key="broken",
            group="app",
            label="Broken",
            description="",
            check=broken_check,
        )
    )
    with pytest.raises(RuntimeError, match="broken"):
        run_checks(TODAY)
    assert Notification.objects.filter(type_key="periodic").exists()


@pytest.mark.django_db
def test_deliver_groups_the_notifications_per_channel(
    user, sample_types, apprise_mock, settings
):
    settings.APP_URL = "https://glad.example.com"
    _only_user(user)
    _channel(user)
    NotificationPreference.objects.create(user=user, type_key="sample", enabled=True)
    run_checks(TODAY)
    apprise_mock.add.assert_called_once_with("ntfy://ntfy.sh/topic")
    kwargs = apprise_mock.notify.call_args.kwargs
    assert kwargs["title"] == "3 new notifications"
    assert "• Alert A 5\n  Body A\n  https://glad.example.com/a/" in kwargs["body"]
    assert not Notification.objects.filter(delivered_at__isnull=True).exists()
    channel = NotificationChannel.objects.get()
    assert channel.last_sent_at is not None
    assert channel.last_error == ""


@pytest.mark.django_db
def test_deliver_respects_the_channels_of_a_type(user, sample_types, apprise_mock):
    _only_user(user)
    phone = _channel(user, "Phone", "ntfy://ntfy.sh/phone")
    _channel(user, "Mail", "mailto://user:pass@example.com")
    pref = NotificationPreference.objects.create(
        user=user, type_key="sample", enabled=True
    )
    pref.channels.add(phone)
    run_checks(TODAY)
    # The phone gets the three notifications, the mail only the periodic one.
    titles = [call.kwargs["title"] for call in apprise_mock.notify.call_args_list]
    assert sorted(titles) == ["3 new notifications", "Periodic"]


@pytest.mark.django_db
def test_disabled_channels_are_skipped(user, sample_types, apprise_mock):
    _only_user(user)
    channel = _channel(user)
    channel.enabled = False
    channel.save()
    run_checks(TODAY)
    apprise_mock.notify.assert_not_called()


def test_format_a_single_notification(settings):
    settings.APP_URL = ""
    notification = Notification(title="Rent late", body="Since 5 days", url="/x/")
    assert format_message([notification]) == ("Rent late", "Since 5 days\n/x/")
    assert format_message([Notification(title="T")]) == ("T", "")


@pytest.mark.django_db
def test_send_to_channel_failures(user):
    channel = _channel(user)
    with patch("apprise.Apprise") as cls:
        cls.return_value.add.return_value = False
        assert not send_to_channel(channel, "T", "B")
        assert "not a valid Apprise URL" in channel.last_error

        cls.return_value.add.return_value = True
        cls.return_value.notify.return_value = False
        assert not send_to_channel(channel, "T", "B")
        assert "refused" in channel.last_error

        cls.return_value.notify.side_effect = OSError("network down")
        assert not send_to_channel(channel, "T", "B")
        assert channel.last_error == "OSError: network down"

    channel.encrypted_url = "garbage"
    assert not send_to_channel(channel, "T", "B")
    assert "cannot be read" in channel.last_error
    assert channel.masked_url == "—"


@pytest.mark.django_db
def test_channel_url_is_encrypted(user):
    channel = _channel(user, url="tgram://123:secret/456")
    channel.refresh_from_db()
    assert "secret" not in channel.encrypted_url
    assert channel.url == "tgram://123:secret/456"
    assert channel.masked_url == "tgram://…"
    assert str(channel) == "Phone"


@pytest.mark.django_db
def test_notify_sends_an_immediate_event(
    user, sample_types, apprise_mock, django_capture_on_commit_callbacks
):
    _only_user(user)
    _channel(user)
    with django_capture_on_commit_callbacks(execute=True):
        created = notify("immediate", Event(key="k", title="Done", level="danger"))
        assert notify("immediate", Event(key="k", title="Done")) == []
    assert [n.title for n in created] == ["Done"]
    apprise_mock.notify.assert_called_once()
    created[0].refresh_from_db()
    assert created[0].delivered_at is not None
    assert str(created[0]) == "Done"


@pytest.mark.django_db
def test_deliver_nothing():
    deliver([])


@pytest.mark.django_db
def test_failed_job_notifies(user, django_capture_on_commit_callbacks):
    _only_user(user)
    job = Job(name="refresh", func="x", label="Refresh", at=datetime.time(6))
    with django_capture_on_commit_callbacks(execute=True):
        job_failed.send(sender=Job, job=job, error=ValueError("bad"))
    notification = Notification.objects.get(user=user, type_key="job_failed")
    assert notification.title == "Background job failed: Refresh"
    assert notification.body == "ValueError: bad"
    assert notification.level == "danger"


@pytest.mark.django_db
def test_failed_email_notifies(user, django_capture_on_commit_callbacks):
    _only_user(user)
    email = SentEmail.objects.create(
        to=["tenant@example.com"], subject="Quittance", body="", error="refused"
    )
    with django_capture_on_commit_callbacks(execute=True):
        email_failed.send(sender=SentEmail, email=email)
    notification = Notification.objects.get(user=user, type_key="email_failed")
    assert notification.title == "Email not sent: Quittance"
    assert notification.body == "To tenant@example.com — refused"


def test_daily_check_job_is_registered(settings):
    from base.scheduler import get_job

    job = get_job("run_notification_checks")
    assert job.func == "notifications.services.run_checks"
    assert job.at == datetime.time(8, 0)


@pytest.mark.django_db
def test_email_channel(user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EMAIL_SUBJECT_PREFIX = "[Glad] "
    from django.core import mail

    channel = NotificationChannel.objects.create(
        user=user, name="Email", kind=NotificationChannel.Kind.EMAIL
    )
    assert channel.url is None
    assert channel.masked_url == "user@site.com"
    assert send_to_channel(channel, "Title", "Body")
    assert mail.outbox[0].subject == "[Glad] Title"
    assert mail.outbox[0].to == ["user@site.com"]

    with patch(
        "notifications.services.EmailMessage.send", side_effect=OSError("refused")
    ):
        assert not send_to_channel(channel, "Title", "Body")
    assert channel.last_error == "OSError: refused"

    user.email = ""
    user.save()
    assert not send_to_channel(channel, "Title", "Body")
    assert channel.last_error == "The account has no email address."


@pytest.mark.django_db
def test_notify_limited_to_some_users(user, admin_user, sample_types):
    User.objects.exclude(pk__in=[user.pk, admin_user.pk]).update(is_active=False)
    created = notify("immediate", Event(key="k", title="Login"), users=[user])
    assert [n.user for n in created] == [user]
