"""URL configuration for the property app."""

from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    path("", views.index, name="index"),
]
