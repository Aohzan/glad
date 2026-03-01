"""URLs for the accounts app."""

from django.urls import path

from .views import LogoutConfirmView, SignUpView

app_name = "accounts"

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("logout_confirm/", LogoutConfirmView.as_view(), name="logout_confirm"),
]
