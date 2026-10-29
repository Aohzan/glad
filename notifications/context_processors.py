"""Unread notification count for the bell of the top bar."""

from notifications.services import unread_count


def unread_notifications(request) -> dict:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notifications": unread_count(user)}
