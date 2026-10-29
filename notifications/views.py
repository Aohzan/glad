"""Inbox and settings of the notifications."""

import datetime

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from notifications.forms import ChannelForm, clean_preferences
from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
)
from notifications.registry import grouped_types, types
from notifications.services import send_to_channel

#: Notifications shown in the drop-down of the top bar.
DROPDOWN_SIZE = 10


def inbox(request: HttpRequest) -> HttpResponse:
    """Every notification of the user, newest first."""
    page = Paginator(Notification.objects.filter(user=request.user), 50).get_page(
        request.GET.get("page")
    )
    return render(request, "notifications/inbox.html", {"page": page})


def dropdown(request: HttpRequest) -> HttpResponse:
    """The latest notifications, for the menu of the top bar."""
    latest = Notification.objects.filter(user=request.user)[:DROPDOWN_SIZE]
    return render(request, "notifications/_dropdown.html", {"latest": latest})


def open_notification(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a notification as read and follow its link."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = datetime.datetime.now()
        notification.save(update_fields=["read_at"])
    url = notification.url
    internal = url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    if url and (internal or url.startswith("https://")):
        return redirect(url)
    return redirect("notifications:inbox")


@require_POST  # type: ignore
def mark_all_read(request: HttpRequest) -> HttpResponse:
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(
        read_at=datetime.datetime.now()
    )
    return redirect("notifications:inbox")


def _settings_context(request: HttpRequest, **extra) -> dict:
    channels = list(
        NotificationChannel.objects.filter(user=request.user).select_related("user")
    )
    stored = {
        pref.type_key: pref
        for pref in NotificationPreference.objects.filter(
            user=request.user
        ).prefetch_related("channels")
    }
    submitted = extra.pop("submitted", None)
    groups = []
    for label, members in grouped_types():
        rows = []
        for notification_type in members:
            pref = stored.get(notification_type.key)
            if submitted is not None:
                values = submitted[notification_type.key]
                enabled = values["enabled"]
                selected = values["channels"]
                raw = {
                    param.key: request.POST.get(f"{notification_type.key}-{param.key}")
                    for param in notification_type.params
                }
            else:
                enabled = pref.enabled if pref else notification_type.default_enabled
                selected = {c.pk for c in pref.channels.all()} if pref else set()
                raw = notification_type.resolve_params(pref.params if pref else None)
            rows.append(
                {
                    "type": notification_type,
                    "enabled": enabled,
                    "channels": selected,
                    "params": [
                        {
                            "param": param,
                            "name": f"{notification_type.key}-{param.key}",
                            "value": raw.get(param.key),
                        }
                        for param in notification_type.params
                    ],
                }
            )
        groups.append({"label": label, "rows": rows})
    return {
        "channels": channels,
        "has_email_channel": any(
            c.kind == NotificationChannel.Kind.EMAIL for c in channels
        ),
        "groups": groups,
        "channel_form": extra.pop("channel_form", None) or ChannelForm(),
        "errors": extra.pop("errors", {}),
        **extra,
    }


def notification_settings(request: HttpRequest) -> HttpResponse:
    """Channels and preferences of the user; saves the preferences on POST."""
    if request.method != "POST":
        return render(
            request, "notifications/settings.html", _settings_context(request)
        )
    channel_ids = set(
        NotificationChannel.objects.filter(user=request.user).values_list(
            "pk", flat=True
        )
    )
    cleaned, errors = clean_preferences(request.POST, types(), channel_ids)
    if errors:
        messages.error(request, _("Some settings are not valid."))
        return render(
            request,
            "notifications/settings.html",
            _settings_context(request, submitted=cleaned, errors=errors),
            status=400,
        )
    with transaction.atomic():
        for key, values in cleaned.items():
            pref, _created = NotificationPreference.objects.update_or_create(
                user=request.user,
                type_key=key,
                defaults={"enabled": values["enabled"], "params": values["params"]},
            )
            pref.channels.set(values["channels"])
    messages.success(request, _("Notification settings saved."))
    return redirect("notifications:settings")


@require_POST  # type: ignore
def add_channel(request: HttpRequest) -> HttpResponse:
    form = ChannelForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "notifications/settings.html",
            _settings_context(request, channel_form=form),
            status=400,
        )
    channel = NotificationChannel(user=request.user, name=form.cleaned_data["name"])
    channel.url = form.cleaned_data["url"]
    channel.save()
    messages.success(request, _("Channel “%(name)s” added.") % {"name": channel.name})
    return redirect(f"{reverse('notifications:settings')}#channels")


@require_POST  # type: ignore
def add_email_channel(request: HttpRequest) -> HttpResponse:
    """Notify the user at the email address of their account."""
    if not getattr(request.user, "email", ""):
        messages.error(request, _("Enter an email address in your settings first."))
    elif not NotificationChannel.objects.filter(
        user=request.user, kind=NotificationChannel.Kind.EMAIL
    ).exists():
        NotificationChannel.objects.create(
            user=request.user, name=_("Email"), kind=NotificationChannel.Kind.EMAIL
        )
        messages.success(request, _("Notifications will also reach you by email."))
    return redirect(f"{reverse('notifications:settings')}#channels")


@require_POST  # type: ignore
def test_channel(request: HttpRequest, pk: int) -> HttpResponse:
    channel = get_object_or_404(NotificationChannel, pk=pk, user=request.user)
    if send_to_channel(
        channel,
        _("Glad test notification"),
        _("Notifications reach you on this channel."),
    ):
        messages.success(
            request, _("Test notification sent to “%(name)s”.") % {"name": channel.name}
        )
    else:
        messages.error(
            request,
            _("The test notification failed: %(error)s")
            % {"error": channel.last_error},
        )
    return redirect(f"{reverse('notifications:settings')}#channels")


@require_POST  # type: ignore
def toggle_channel(request: HttpRequest, pk: int) -> HttpResponse:
    channel = get_object_or_404(NotificationChannel, pk=pk, user=request.user)
    channel.enabled = not channel.enabled
    channel.save(update_fields=["enabled", "updated_at"])
    return redirect(f"{reverse('notifications:settings')}#channels")


@require_POST  # type: ignore
def delete_channel(request: HttpRequest, pk: int) -> HttpResponse:
    channel = get_object_or_404(NotificationChannel, pk=pk, user=request.user)
    channel.delete()
    messages.success(request, _("Channel “%(name)s” deleted.") % {"name": channel.name})
    return redirect(f"{reverse('notifications:settings')}#channels")
