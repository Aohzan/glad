"""URLs for the accounts app."""

from django.urls import path

from .views import (
    LogoutConfirmView,
    SettingsView,
    passkey_auth_complete,
    passkey_auth_options,
    passkey_delete,
    passkey_register_complete,
    passkey_register_options,
    update_email,
    update_notification_preferences,
    update_session_timeout,
)

app_name = "accounts"

urlpatterns = [
    path("logout_confirm/", LogoutConfirmView.as_view(), name="logout_confirm"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path(
        "api/passkey/register/options/",
        passkey_register_options,
        name="passkey_register_options",
    ),
    path(
        "api/passkey/register/complete/",
        passkey_register_complete,
        name="passkey_register_complete",
    ),
    path(
        "api/passkey/auth/options/",
        passkey_auth_options,
        name="passkey_auth_options",
    ),
    path(
        "api/passkey/auth/complete/",
        passkey_auth_complete,
        name="passkey_auth_complete",
    ),
    path(
        "api/passkey/delete/",
        passkey_delete,
        name="passkey_delete",
    ),
    path(
        "api/session-timeout/update/",
        update_session_timeout,
        name="update_session_timeout",
    ),
    path(
        "api/email/update/",
        update_email,
        name="update_email",
    ),
    path(
        "api/notification-preferences/update/",
        update_notification_preferences,
        name="update_notification_preferences",
    ),
]
