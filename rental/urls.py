"""URL configuration for the rental app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from . import views

app_name = "rental"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("lease/<int:pk>/", views.lease_detail, name="lease_detail"),
    path("lease/<int:pk>/documents/", views.lease_documents, name="lease_documents"),
    path(
        "lease/<int:pk>/documents/upload/",
        cast(Callable[..., HttpResponseBase], views.upload_lease_document),
        name="upload_lease_document",
    ),
    path("lease/<int:pk>/payments/", views.lease_payments, name="lease_payments"),
    path(
        "lease/<int:pk>/schedule/",
        cast(Callable[..., HttpResponseBase], views.create_schedule),
        name="create_schedule",
    ),
    path(
        "lease/<int:pk>/receipt/<str:period>/",
        views.download_receipt,
        name="download_receipt",
    ),
    path("lease/<int:pk>/emails/", views.lease_emails, name="lease_emails"),
    path(
        "lease/<int:pk>/emails/<str:kind>/", views.compose_email, name="compose_email"
    ),
    path("lease/<int:lease_pk>/party/new/", views.edit_party, name="new_party"),
    path(
        "lease/<int:lease_pk>/party/<int:pk>/edit/",
        views.edit_party,
        name="edit_party",
    ),
    path(
        "lease/<int:lease_pk>/party/<int:pk>/delete/",
        cast(Callable[..., HttpResponseBase], views.delete_party),
        name="delete_party",
    ),
]
