"""URLs of the notifications app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from notifications import views

app_name = "notifications"


def _post(view) -> Callable[..., HttpResponseBase]:
    return cast(Callable[..., HttpResponseBase], view)


urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("menu/", views.dropdown, name="dropdown"),
    path("read-all/", _post(views.mark_all_read), name="mark_all_read"),
    path("<int:pk>/open/", views.open_notification, name="open"),
    path("settings/", views.notification_settings, name="settings"),
    path("channels/add/", _post(views.add_channel), name="add_channel"),
    path(
        "channels/add-email/",
        _post(views.add_email_channel),
        name="add_email_channel",
    ),
    path("channels/<int:pk>/test/", _post(views.test_channel), name="test_channel"),
    path(
        "channels/<int:pk>/toggle/",
        _post(views.toggle_channel),
        name="toggle_channel",
    ),
    path(
        "channels/<int:pk>/delete/",
        _post(views.delete_channel),
        name="delete_channel",
    ),
]
