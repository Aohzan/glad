"""Signals for the accounts app."""

import logging
import socket
import threading

from django.contrib.auth.signals import user_logged_in
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import UserProfile

_LOGGER = logging.getLogger(__name__)


_EMAIL_TIMEOUT = 10


def _send_email_async(subject, text_body, html_body, recipient):
    socket.setdefaulttimeout(_EMAIL_TIMEOUT)
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            to=[recipient],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
        _LOGGER.info("Login notification sent to %s", recipient)
    except Exception:
        _LOGGER.exception("Failed to send login notification to %s", recipient)


def send_login_notification(sender, user, request, **kwargs):
    """Send a login notification email when a user logs in."""
    try:
        profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        return

    if not profile.notify_on_login:
        return

    if not user.email:
        return

    ip_address = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    login_time = timezone.now()

    context = {
        "user": user,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "login_time": login_time,
        "settings_url": _build_settings_url(request),
    }

    try:
        subject = render_to_string(
            "accounts/emails/login_notification_subject.txt", context
        ).strip()
        text_body = render_to_string("accounts/emails/login_notification.txt", context)
        html_body = render_to_string("accounts/emails/login_notification.html", context)

        thread = threading.Thread(
            target=_send_email_async,
            args=(subject, text_body, html_body, user.email),
            daemon=True,
        )
        thread.start()
    except Exception:
        _LOGGER.exception("Failed to prepare login notification to %s", user.email)


def _get_client_ip(request):
    """Extract the client IP address from the request."""
    if x_forwarded_for := request.META.get("HTTP_X_FORWARDED_FOR"):
        return x_forwarded_for.split(",")[0].strip()
    if x_real_ip := request.META.get("HTTP_X_REAL_IP"):
        return x_real_ip.strip()
    return request.META.get("REMOTE_ADDR", "")


def _build_settings_url(request):
    """Build the full URL to the user settings page."""
    try:
        from django.conf import settings
        from django.urls import reverse

        path = reverse("accounts:settings")
        app_url = getattr(settings, "APP_URL", None)
        if app_url:
            return f"{app_url.rstrip('/')}{path}"
        if request is None:
            return ""
        scheme = "https" if request.is_secure() else "http"
        host = request.get_host()
        return f"{scheme}://{host}{path}"
    except Exception:
        return ""


user_logged_in.connect(send_login_notification)
