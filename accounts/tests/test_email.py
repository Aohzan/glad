"""Tests for accounts email signals."""

import os
import threading
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import RequestFactory, override_settings

from accounts.models import UserProfile
from accounts.signals import _EMAIL_TIMEOUT, _send_email_async

User = get_user_model()


def _trigger_login_notification(user, request):
    user_logged_in.send(sender=user.__class__, user=user, request=request)
    for thread in threading.enumerate():
        if (
            thread is not threading.main_thread()
            and thread.is_alive()
            and thread.daemon
        ):
            thread.join(timeout=5)


@pytest.mark.django_db
def test_login_notification_sent_when_enabled(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    with patch("accounts.signals.threading.Thread.start") as mock_start:
        user_logged_in.send(sender=user.__class__, user=user, request=request)
        mock_start.assert_called_once()


@pytest.mark.django_db
def test_login_notification_not_sent_when_disabled(user):
    user.email = "test@example.com"
    user.save()
    profile = UserProfile.objects.get(user=user)
    profile.notify_on_login = False
    profile.save(update_fields=["notify_on_login"])

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    with patch("accounts.signals.threading.Thread.start") as mock_start:
        user_logged_in.send(sender=user.__class__, user=user, request=request)
        mock_start.assert_not_called()


@pytest.mark.django_db
def test_login_notification_not_sent_when_no_email(user):
    user.email = ""
    user.save(update_fields=["email"])
    profile = UserProfile.objects.get(user=user)
    profile.notify_on_login = True
    profile.save(update_fields=["notify_on_login"])

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    with patch("accounts.signals.threading.Thread.start") as mock_start:
        user_logged_in.send(sender=user.__class__, user=user, request=request)
        mock_start.assert_not_called()


@pytest.mark.django_db
def test_login_notification_not_sent_when_profile_missing(user):
    user.email = "test@example.com"
    user.save(update_fields=["email"])
    UserProfile.objects.filter(user=user).delete()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    with patch("accounts.signals.threading.Thread.start") as mock_start:
        user_logged_in.send(sender=user.__class__, user=user, request=request)
        mock_start.assert_not_called()


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

    with patch("accounts.signals.threading.Thread") as MockThread:
        instance = MockThread.return_value
        instance.start.return_value = None

        user_logged_in.send(sender=user.__class__, user=user, request=request)

        MockThread.assert_called_once()
        call_kwargs = MockThread.call_args
        assert call_kwargs[1]["target"] is _send_email_async
        args = call_kwargs[1]["args"]
        assert "9.8.7.6" in args[1]
        assert "9.8.7.6" in args[2]
        assert "10.0.0.1" not in args[1]


@pytest.mark.django_db
def test_login_notification_includes_html_alternative(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    with patch("accounts.signals.threading.Thread") as MockThread:
        instance = MockThread.return_value
        instance.start.return_value = None

        user_logged_in.send(sender=user.__class__, user=user, request=request)

        MockThread.assert_called_once()
        call_kwargs = MockThread.call_args
        args = call_kwargs[1]["args"]
        assert args[3] == "test@example.com"
        assert "<" in args[2]


@pytest.mark.django_db
def test_login_notification_failure_does_not_raise(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    with patch(
        "accounts.signals.EmailMultiAlternatives.send",
        side_effect=Exception("SMTP error"),
    ):
        _send_email_async("Subject", "Body", "<p>Body</p>", "test@example.com")


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

    with patch("accounts.signals.threading.Thread") as MockThread:
        instance = MockThread.return_value
        instance.start.return_value = None

        user_logged_in.send(sender=user.__class__, user=user, request=request)

        MockThread.assert_called_once()
        call_kwargs = MockThread.call_args
        args = call_kwargs[1]["args"]
        assert "/accounts/settings/" in args[2]


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


def test_email_backend_console_when_no_host():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EMAIL_HOST", None)
        email_host = os.getenv("EMAIL_HOST")
        assert not email_host


def test_email_backend_smtp_when_host_set():
    with patch.dict(
        os.environ, {"EMAIL_HOST": "smtp.example.com", "EMAIL_PORT": "587"}
    ):
        assert os.getenv("EMAIL_HOST") == "smtp.example.com"
        assert os.getenv("EMAIL_PORT") == "587"


@pytest.mark.django_db
def test_email_backend_smtp_sends_via_smtp(user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    with patch("accounts.signals.threading.Thread") as MockThread:
        instance = MockThread.return_value
        instance.start.return_value = None

        user_logged_in.send(sender=user.__class__, user=user, request=request)

        MockThread.assert_called_once()


@pytest.mark.django_db
def test_send_email_async_constructs_email(user):
    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    ):
        _send_email_async(
            "Test Subject", "Text body", "<p>HTML body</p>", "test@example.com"
        )
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert isinstance(msg, EmailMultiAlternatives)
        assert msg.subject == "Test Subject"
        assert msg.body == "Text body"
        assert msg.to == ["test@example.com"]
        assert len(msg.alternatives) == 1
        assert msg.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_send_email_async_logs_on_failure():
    with patch(
        "accounts.signals.EmailMultiAlternatives.send",
        side_effect=Exception("SMTP error"),
    ):
        with patch("accounts.signals._LOGGER") as mock_logger:
            _send_email_async("Subject", "Body", "<p>Body</p>", "fail@example.com")
            mock_logger.exception.assert_called_once()


@pytest.mark.django_db
def test_login_notification_template_render_failure_does_not_raise(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")

    with patch(
        "accounts.signals.render_to_string",
        side_effect=Exception("Template error"),
    ):
        user_logged_in.send(sender=user.__class__, user=user, request=request)


@pytest.mark.django_db
def test_login_notification_thread_is_daemon(user):
    user.email = "test@example.com"
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_login = True
    profile.save()

    request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"

    with patch("accounts.signals.threading.Thread") as MockThread:
        instance = MockThread.return_value
        instance.start.return_value = None

        user_logged_in.send(sender=user.__class__, user=user, request=request)

        MockThread.assert_called_once()
        call_kwargs = MockThread.call_args
        assert call_kwargs[1]["daemon"] is True


def test_email_timeout_is_10_seconds():
    assert _EMAIL_TIMEOUT == 10


@pytest.mark.django_db
def test_send_email_async_sets_socket_timeout():
    import socket

    original_timeout = socket.getdefaulttimeout()
    try:
        with patch("accounts.signals.EmailMultiAlternatives.send") as mock_send:
            _send_email_async("Subject", "Body", "<p>Body</p>", "test@example.com")
            mock_send.assert_called_once()
            assert socket.getdefaulttimeout() == _EMAIL_TIMEOUT
    finally:
        socket.setdefaulttimeout(original_timeout)


@pytest.mark.django_db
def test_send_email_async_timeout_does_not_affect_main_thread():
    import socket

    original_timeout = socket.getdefaulttimeout()
    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    ):
        _send_email_async("Subject", "Body", "<p>Body</p>", "test@example.com")
        assert socket.getdefaulttimeout() == original_timeout
