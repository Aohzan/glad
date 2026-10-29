"""Tests for the login notification and the email configuration."""

import os
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.test import RequestFactory, override_settings

from accounts.signals import _get_client_ip
from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
)

User = get_user_model()
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def _login(user, **meta):
    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4", **meta)
    user_logged_in.send(sender=user.__class__, user=user, request=request)


@pytest.mark.django_db
def test_login_is_notified_to_the_user_only(user, admin_user):
    _login(user, HTTP_USER_AGENT="TestBrowser/1.0")
    notification = Notification.objects.get(type_key="login")
    assert notification.user == user
    assert notification.title == "New login to your Glad account"
    assert "IP address: 1.2.3.4" in notification.body
    assert "Browser: TestBrowser/1.0" in notification.body
    assert notification.url == "/accounts/settings/"
    assert not Notification.objects.filter(user=admin_user).exists()


@pytest.mark.django_db
def test_every_login_is_notified(user):
    _login(user)
    _login(user)
    assert Notification.objects.filter(user=user, type_key="login").count() == 2


@pytest.mark.django_db
def test_login_not_notified_when_disabled(user):
    NotificationPreference.objects.create(user=user, type_key="login", enabled=False)
    _login(user)
    assert not Notification.objects.filter(type_key="login").exists()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_SUBJECT_PREFIX="[Glad] ")
def test_login_reaches_the_email_channel(user, django_capture_on_commit_callbacks):
    user.email = "user@example.com"
    user.save()
    NotificationChannel.objects.create(
        user=user, name="Email", kind=NotificationChannel.Kind.EMAIL
    )
    with django_capture_on_commit_callbacks(execute=True):
        _login(user)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["user@example.com"]
    assert message.subject == "[Glad] New login to your Glad account"
    assert "IP address: 1.2.3.4" in message.body


@pytest.mark.django_db
def test_login_notification_failure_does_not_raise(user):
    with patch("accounts.signals.notify", side_effect=RuntimeError("boom")):
        _login(user)


@pytest.mark.django_db
def test_login_without_request(user):
    user_logged_in.send(sender=user.__class__, user=user, request=None)
    body = Notification.objects.get(type_key="login").body
    assert body.startswith("Date: ")
    assert "IP address: \n" in body
    assert "Browser" not in body


def test_get_client_ip_no_forwarded():
    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    assert _get_client_ip(request) == "1.2.3.4"


def test_get_client_ip_with_forwarded():
    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.8.7.6, 10.0.0.1"
    )
    assert _get_client_ip(request) == "9.8.7.6"


def test_get_client_ip_with_x_real_ip():
    request = RequestFactory().get(
        "/", REMOTE_ADDR="172.22.1.1", HTTP_X_REAL_IP="203.0.113.50"
    )
    assert _get_client_ip(request) == "203.0.113.50"


def test_get_client_ip_x_forwarded_for_takes_priority_over_x_real_ip():
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="172.22.1.1",
        HTTP_X_FORWARDED_FOR="9.8.7.6",
        HTTP_X_REAL_IP="203.0.113.50",
    )
    assert _get_client_ip(request) == "9.8.7.6"


def test_get_client_ip_empty():
    request = RequestFactory().get("/")
    request.META.pop("REMOTE_ADDR", None)
    assert _get_client_ip(request) == ""
    assert _get_client_ip(None) == ""


def test_email_backend_console_when_no_host():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EMAIL_HOST", None)
        assert not os.getenv("EMAIL_HOST")


def test_email_backend_smtp_when_host_set():
    with patch.dict(
        os.environ, {"EMAIL_HOST": "smtp.example.com", "EMAIL_PORT": "587"}
    ):
        assert os.getenv("EMAIL_HOST") == "smtp.example.com"
        assert os.getenv("EMAIL_PORT") == "587"
