"""Signals for the accounts app."""

import datetime
import logging
import uuid

from django.contrib.auth.signals import user_logged_in
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from base.services.network import client_ip
from notifications.registry import Event
from notifications.services import notify

_LOGGER = logging.getLogger(__name__)


def send_login_notification(sender, user, request, **kwargs):
    """Notify a user that someone logged in to their account."""
    try:
        lines = [
            _("Date: %(date)s")
            % {"date": date_format(datetime.datetime.now(), "DATETIME_FORMAT")},
            _("IP address: %(ip)s") % {"ip": _get_client_ip(request)},
        ]
        if user_agent := request.META.get("HTTP_USER_AGENT", "") if request else "":
            lines.append(_("Browser: %(agent)s") % {"agent": user_agent[:200]})
        lines.append(
            _("If this was not you, change your password and review your passkey.")
        )
        notify(
            "login",
            Event(
                key=uuid.uuid4().hex,
                title=_("New login to your Glad account"),
                body="\n".join(lines),
                url=reverse("accounts:settings"),
            ),
            users=[user],
        )
    except Exception:
        _LOGGER.exception("Failed to notify the login of %s", user)


def _get_client_ip(request):
    """Extract the client IP address from the request."""
    return "" if request is None else client_ip(request.META)


user_logged_in.connect(send_login_notification)
