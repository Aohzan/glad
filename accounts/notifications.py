"""Notification types about the user accounts."""

from django.utils.translation import gettext_lazy

from notifications.registry import NotificationType, register

register(
    NotificationType(
        key="login",
        group="app",
        label=gettext_lazy("Login"),
        description=gettext_lazy(
            "Someone logged in to your account (sent to you only). "
            "Choose a channel outside the application, such as your email."
        ),
    )
)
