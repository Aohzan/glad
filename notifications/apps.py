"""Configuration of the notifications app."""

import datetime

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    """Load the notification types of every app and declare the daily check."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = _("Notifications")

    def ready(self):
        from django.conf import settings

        import notifications.receivers  # noqa: F401
        from base.scheduler import Job, register

        autodiscover_modules("notifications")
        hour, minute = (int(part) for part in settings.NOTIFICATIONS_TIME.split(":"))
        register(
            Job(
                name="run_notification_checks",
                func="notifications.services.run_checks",
                label=_("Check and send the notifications"),
                at=datetime.time(hour, minute),
            )
        )
