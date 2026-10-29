"""Notification channels, preferences and inbox of each user."""

from urllib.parse import urlsplit

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel
from base.services.crypto import decrypt, encrypt


class NotificationChannel(BaseModel):
    """Where a user is notified: an Apprise URL (ntfy, Gotify, Telegram…), or
    the email address of the account, through the SMTP server of the application.

    An Apprise URL often holds a token, so it is stored encrypted and never
    shown back in full.
    """

    class Kind(models.TextChoices):
        APPRISE = "apprise", _("Apprise URL")
        EMAIL = "email", _("Email of the account")

    class Meta:
        verbose_name = _("notification channel")
        verbose_name_plural = _("notification channels")
        ordering = ["name", "pk"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_channels",
    )
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.APPRISE)
    encrypted_url = models.TextField(blank=True)
    enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))
    last_error = models.TextField(blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    @property
    def url(self) -> str | None:
        """The Apprise URL, None when it cannot be decrypted (SECRET_KEY changed)."""
        if self.kind == self.Kind.EMAIL:
            return None
        return decrypt(self.encrypted_url)

    @url.setter
    def url(self, value: str) -> None:
        self.encrypted_url = encrypt(value)

    @property
    def masked_url(self) -> str:
        """The service of the URL without its secrets, e.g. ``ntfy://…``."""
        if self.kind == self.Kind.EMAIL:
            return self.user.email
        url = self.url
        if url is None:
            return "—"
        scheme = urlsplit(url).scheme
        return f"{scheme}://…" if scheme else "…"


class NotificationPreference(BaseModel):
    """Whether a user receives a type of notification, with its settings."""

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type_key"], name="unique_notification_preference"
            )
        ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    type_key = models.CharField(max_length=50)
    enabled = models.BooleanField(default=False)
    params = models.JSONField(default=dict, blank=True)
    #: Channels to send this type to; none means every enabled channel.
    channels = models.ManyToManyField(NotificationChannel, blank=True)

    def __str__(self) -> str:
        return f"{self.user} {self.type_key}"


class Notification(models.Model):
    """A notification in the inbox of a user.

    ``dedup_key`` identifies the event, so the same event never notifies a
    user twice.
    """

    class Level(models.TextChoices):
        INFO = "info", _("Information")
        WARNING = "warning", _("Warning")
        DANGER = "danger", _("Alert")

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedup_key"], name="unique_notification_event"
            )
        ]
        indexes = [models.Index(fields=["user", "read_at"])]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type_key = models.CharField(max_length=50)
    dedup_key = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.title
