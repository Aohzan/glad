"""Tests for accounts email signals."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import RequestFactory

from accounts.models import UserProfile

User = get_user_model()


@pytest.mark.django_db
def test_login_notification_sent_when_enabled(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 1
    assert user.email in mail.outbox[0].to
    assert "1.2.3.4" in mail.outbox[0].body
    assert "TestBrowser/1.0" in mail.outbox[0].body


@pytest.mark.django_db
def test_login_notification_not_sent_when_disabled(user):
    user.email = "test@example.com"
    user.save()
    profile = UserProfile.objects.get(user=user)
    profile.notify_on_login = False
    profile.save(update_fields=["notify_on_login"])

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_login_notification_not_sent_when_no_email(user):
    user.email = ""
    user.save(update_fields=["email"])
    profile = UserProfile.objects.get(user=user)
    profile.notify_on_login = True
    profile.save(update_fields=["notify_on_login"])

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_login_notification_not_sent_when_profile_missing(user):
    user.email = "test@example.com"
    user.save(update_fields=["email"])
    UserProfile.objects.filter(user=user).delete()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_login_notification_uses_x_forwarded_for(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.8.7.6, 10.0.0.1"
    )
    request.META["HTTP_USER_AGENT"] = "ProxyBrowser/2.0"

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 1
    assert "9.8.7.6" in mail.outbox[0].body
    assert "10.0.0.1" not in mail.outbox[0].body


@pytest.mark.django_db
def test_login_notification_includes_html_alternative(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert isinstance(msg, EmailMultiAlternatives)
    assert len(msg.alternatives) == 1
    assert msg.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_login_notification_failure_does_not_raise(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    with patch(
        "accounts.signals.EmailMultiAlternatives.send",
        side_effect=Exception("SMTP error"),
    ):
        user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_login_notification_settings_url(user, settings):
    settings.APP_URL = "https://example.com"
    settings.ALLOWED_HOSTS = ["example.com", "localhost", "127.0.0.1"]
    user.email = "test@example.com"
    user.save()
    profile = UserProfile.objects.get(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", secure=True, HTTP_HOST="example.com")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    user_logged_in.send(sender=user.__class__, user=user, request=request)

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert isinstance(msg, EmailMultiAlternatives)
    assert "/accounts/settings/" in str(msg.alternatives[0][0])


def test_get_client_ip_no_forwarded():
    from accounts.signals import _get_client_ip

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    assert _get_client_ip(request) == "1.2.3.4"


def test_get_client_ip_with_forwarded():
    from accounts.signals import _get_client_ip

    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.8.7.6, 10.0.0.1"
    )
    assert _get_client_ip(request) == "9.8.7.6"


def test_get_client_ip_empty():
    from accounts.signals import _get_client_ip

    request = RequestFactory().get("/")
    request.META.pop("REMOTE_ADDR", None)
    assert _get_client_ip(request) == ""
