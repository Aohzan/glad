"""Run the notification checks and deliver the notifications.

The checks run once for the household (the data is shared), once per distinct
set of settings among the subscribers. Each new notification lands in the
user's inbox, then one message per channel groups the new notifications of
the user.
"""

import datetime
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.db import transaction
from django.tasks import task
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
lazy import apprise

from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
)
from notifications.registry import Event, NotificationType, get_type, types

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """A user receiving a type of notification, with their settings."""

    user: Any
    params: dict[str, Any]
    #: Channels chosen for the type; empty means every enabled channel.
    channel_ids: list[int]


def household_users():
    """Users who can receive notifications: the active adults."""
    return (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(profile__is_child=True)
        .order_by("pk")
    )


def subscriptions(notification_type: NotificationType) -> list[Subscription]:
    """The users who receive *notification_type*."""
    preferences = {
        pref.user_id: pref
        for pref in NotificationPreference.objects.filter(
            type_key=notification_type.key
        ).prefetch_related("channels")
    }
    result = []
    for user in household_users():
        pref = preferences.get(user.pk)
        enabled = pref.enabled if pref else notification_type.default_enabled
        if not enabled:
            continue
        result.append(
            Subscription(
                user=user,
                params=notification_type.resolve_params(pref.params if pref else None),
                channel_ids=[c.pk for c in pref.channels.all()] if pref else [],
            )
        )
    return result


def _record(
    notification_type: NotificationType,
    events: Iterable[Event],
    subscribers: Iterable[Subscription],
    today: datetime.date,
) -> list[Notification]:
    """Store the events not notified yet; the new notifications."""
    created = []
    events = list(events)
    for subscription in subscribers:
        for event in events:
            if _notified_recently(notification_type, event, subscription.user, today):
                continue
            notification, new = Notification.objects.get_or_create(
                user=subscription.user,
                dedup_key=notification_type.dedup_key(event, today),
                defaults={
                    "type_key": notification_type.key,
                    "title": str(event.title)[:255],
                    "body": str(event.body),
                    "url": event.url[:500],
                    "level": event.level,
                },
            )
            if new:
                created.append(notification)
    return created


def _notified_recently(
    notification_type: NotificationType, event: Event, user, today: datetime.date
) -> bool:
    """Whether a renotified event was notified less than ``renotify_days`` ago."""
    if not notification_type.renotify_days:
        return False  # the dedup key alone prevents a second notification
    prefix = f"{notification_type.base_key(event)}@"
    since = today - datetime.timedelta(days=notification_type.renotify_days)
    return Notification.objects.filter(
        user=user,
        dedup_key__startswith=prefix,
        dedup_key__gt=f"{prefix}{since.isoformat()}",
    ).exists()


def run_checks(today: datetime.date | None = None) -> str:
    """Run every check for its subscribers and deliver what is new."""
    today = today or datetime.date.today()
    created: list[Notification] = []
    failures = []
    with translation.override(settings.LANGUAGE_CODE):
        for notification_type in types():
            if notification_type.check is None:
                continue
            by_params: dict[str, list[Subscription]] = defaultdict(list)
            for subscription in subscriptions(notification_type):
                key = json.dumps(subscription.params, sort_keys=True, default=str)
                by_params[key].append(subscription)
            for subscribers in by_params.values():
                try:
                    events = list(notification_type.check(subscribers[0].params, today))
                except Exception:
                    logger.exception(
                        "Notification check %s failed", notification_type.key
                    )
                    failures.append(notification_type.key)
                    break
                created += _record(notification_type, events, subscribers, today)
        deliver(created)
    if failures:
        raise RuntimeError(f"Notification checks failed: {', '.join(failures)}")
    return f"{len(created)} notification(s)"


def notify(
    type_key: str,
    event: Event,
    today: datetime.date | None = None,
    users: Iterable[Any] | None = None,
) -> list[Notification]:
    """Notify the subscribers of *type_key* of an event that just happened.

    *users* limits the notification to some subscribers (an event about one
    account, such as a login).
    """
    today = today or datetime.date.today()
    notification_type = get_type(type_key)
    subscribers = subscriptions(notification_type)
    if users is not None:
        allowed = {user.pk for user in users}
        subscribers = [s for s in subscribers if s.user.pk in allowed]
    created = _record(notification_type, [event], subscribers, today)
    if created:
        ids = [n.pk for n in created]
        transaction.on_commit(lambda: deliver_notifications.enqueue(ids))
    return created


@task
def deliver_notifications(notification_ids: list[int]) -> None:
    """Send stored notifications to the channels of their users."""
    with translation.override(settings.LANGUAGE_CODE):
        deliver(
            Notification.objects.filter(
                pk__in=notification_ids, delivered_at__isnull=True
            )
        )


def _absolute(url: str) -> str:
    if url.startswith("/") and settings.APP_URL:
        return settings.APP_URL.rstrip("/") + url
    return url


def format_message(notifications: list[Notification]) -> tuple[str, str]:
    """Title and body of one message grouping *notifications*."""
    if len(notifications) == 1:
        notification = notifications[0]
        lines = [notification.body] if notification.body else []
        if notification.url:
            lines.append(_absolute(notification.url))
        return notification.title, "\n".join(lines)
    title = ngettext(
        "%(count)d new notification", "%(count)d new notifications", len(notifications)
    ) % {"count": len(notifications)}
    blocks = []
    for notification in notifications:
        lines = [f"• {notification.title}"]
        if notification.body:
            lines.append(f"  {notification.body}")
        if notification.url:
            lines.append(f"  {_absolute(notification.url)}")
        blocks.append("\n".join(lines))
    return title, "\n".join(blocks)


def _send_email(channel: NotificationChannel, title: str, body: str) -> str:
    """Email the message to the account of *channel*; the error, if any."""
    address = channel.user.email
    if not address:
        return _("The account has no email address.")
    try:
        EmailMessage(
            subject=f"{settings.EMAIL_SUBJECT_PREFIX}{title}".replace("\n", " "),
            body=body,
            to=[address],
        ).send(fail_silently=False)
    except Exception as exc:
        logger.warning("Email channel %s failed", channel.pk, exc_info=True)
        return f"{type(exc).__name__}: {exc}"
    return ""


def send_to_channel(channel: NotificationChannel, title: str, body: str) -> bool:
    """Send a message to *channel*, recording the error when it fails."""
    url = channel.url
    error = ""
    if channel.kind == NotificationChannel.Kind.EMAIL:
        error = _send_email(channel, title, body)
    elif url is None:
        error = _("The URL cannot be read anymore: enter it again.")
    else:
        sender = apprise.Apprise()
        if not sender.add(url):
            error = _("The URL is not a valid Apprise URL.")
        else:
            try:
                if not sender.notify(title=title, body=body):
                    error = _("The service refused the message.")
            except Exception as exc:
                logger.warning("Channel %s failed", channel.pk, exc_info=True)
                error = f"{type(exc).__name__}: {exc}"
    channel.last_error = str(error)
    fields = ["last_error", "updated_at"]
    if not error:
        channel.last_sent_at = datetime.datetime.now()
        fields.append("last_sent_at")
    channel.save(update_fields=fields)
    return not error


def deliver(notifications: Iterable[Notification]) -> None:
    """Group the notifications of each user into one message per channel."""
    by_user: dict[int, list[Notification]] = defaultdict(list)
    for notification in notifications:
        by_user[notification.user_id].append(notification)
    if not by_user:
        return
    channels: dict[int, list[NotificationChannel]] = defaultdict(list)
    for channel in NotificationChannel.objects.filter(
        user_id__in=by_user, enabled=True
    ).select_related("user"):
        channels[channel.user_id].append(channel)
    restrictions: dict[tuple[int, str], set[int]] = {}
    for pref in NotificationPreference.objects.filter(
        user_id__in=by_user
    ).prefetch_related("channels"):
        restrictions[(pref.user_id, pref.type_key)] = {
            c.pk for c in pref.channels.all()
        }
    now = datetime.datetime.now()
    for user_id, user_notifications in by_user.items():
        for channel in channels[user_id]:
            selected = [
                n
                for n in user_notifications
                if not restrictions.get((user_id, n.type_key))
                or channel.pk in restrictions[(user_id, n.type_key)]
            ]
            if selected:
                send_to_channel(channel, *format_message(selected))
        Notification.objects.filter(pk__in=[n.pk for n in user_notifications]).update(
            delivered_at=now
        )


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
