"""URLs of the MCP access settings (the MCP endpoint itself is /mcp, see glad.asgi)."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from mcp_server import views

app_name = "mcp_server"


def _post(view) -> Callable[..., HttpResponseBase]:
    return cast(Callable[..., HttpResponseBase], view)


urlpatterns = [
    path("", views.mcp_settings, name="settings"),
    path("keys/add/", _post(views.add_key), name="add_key"),
    path("keys/<int:pk>/toggle/", _post(views.toggle_key), name="toggle_key"),
    path("keys/<int:pk>/delete/", _post(views.delete_key), name="delete_key"),
]
