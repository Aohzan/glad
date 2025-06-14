"""URL configuration for the base app."""

from django.urls import path

from base import views

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
]
