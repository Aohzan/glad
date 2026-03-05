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
    passkey_verify_complete,
    passkey_verify_options,
    password_verify,
    toggle_app_lock,
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
        "api/passkey/verify/options/",
        passkey_verify_options,
        name="passkey_verify_options",
    ),
    path(
        "api/passkey/verify/complete/",
        passkey_verify_complete,
        name="passkey_verify_complete",
    ),
    path(
        "api/app-lock/toggle/",
        toggle_app_lock,
        name="toggle_app_lock",
    ),
    path(
        "api/password/verify/",
        password_verify,
        name="password_verify",
    ),
]
