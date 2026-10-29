"""URL configuration for the rental app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from . import (
    application_views,
    charges_views,
    inventory_views,
    signature_views,
    views,
)

app_name = "rental"


def _post(view) -> Callable[..., HttpResponseBase]:
    """A ``require_POST`` view, typed for ``path``."""
    return cast(Callable[..., HttpResponseBase], view)


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("lease/<int:pk>/", views.lease_detail, name="lease_detail"),
    path("lease/<int:pk>/documents/", views.lease_documents, name="lease_documents"),
    path(
        "lease/<int:pk>/documents/upload/",
        _post(views.upload_lease_document),
        name="upload_lease_document",
    ),
    path("lease/<int:pk>/payments/", views.lease_payments, name="lease_payments"),
    path(
        "lease/<int:pk>/schedule/",
        _post(views.create_schedule),
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
    # Lease PDF, signatures and move-in
    path("lease/<int:pk>/pdf/", signature_views.lease_download, name="lease_pdf"),
    path("lease/<int:pk>/sign/", _post(signature_views.sign_lease), name="sign_lease"),
    path(
        "lease/<int:pk>/deposit/",
        _post(signature_views.receive_deposit),
        name="receive_deposit",
    ),
    path(
        "signature/<int:pk>/refresh/",
        _post(signature_views.refresh_signature),
        name="refresh_signature",
    ),
    # Inventories
    path(
        "lease/<int:pk>/inventories/",
        inventory_views.lease_inventories,
        name="lease_inventories",
    ),
    path(
        "lease/<int:pk>/inventories/new/<str:kind>/",
        _post(inventory_views.create_inventory),
        name="create_inventory",
    ),
    path(
        "inventory/<int:pk>/",
        inventory_views.inventory_detail,
        name="inventory_detail",
    ),
    path(
        "inventory/<int:pk>/pdf/",
        inventory_views.inventory_download,
        name="inventory_pdf",
    ),
    path(
        "inventory/<int:pk>/sign/",
        _post(signature_views.sign_inventory),
        name="sign_inventory",
    ),
    path(
        "inventory/<int:pk>/room/new/",
        _post(inventory_views.add_room),
        name="inventory_add_room",
    ),
    path(
        "inventory/<int:pk>/room/<int:room_pk>/",
        inventory_views.inventory_room,
        name="inventory_room",
    ),
    path(
        "inventory/<int:pk>/room/<int:room_pk>/delete/",
        _post(inventory_views.delete_room),
        name="inventory_delete_room",
    ),
    path(
        "inventory/<int:pk>/room/<int:room_pk>/item/new/",
        _post(inventory_views.add_item),
        name="inventory_add_item",
    ),
    path(
        "inventory/<int:pk>/item/<int:item_pk>/delete/",
        _post(inventory_views.delete_item),
        name="inventory_delete_item",
    ),
    path(
        "inventory/<int:pk>/item/<int:item_pk>/photo/",
        _post(inventory_views.add_photo),
        name="inventory_add_photo",
    ),
    # Charges reconciliation
    path("lease/<int:pk>/charges/", charges_views.lease_charges, name="lease_charges"),
    path(
        "lease/<int:pk>/charges/new/",
        _post(charges_views.create_reconciliation),
        name="create_reconciliation",
    ),
    path(
        "charges/<int:pk>/",
        charges_views.reconciliation_detail,
        name="reconciliation_detail",
    ),
    path("charges/<int:pk>/pdf/", charges_views.reconciliation_pdf, name="charges_pdf"),
    path(
        "charges/<int:pk>/record/",
        _post(charges_views.record_reconciliation),
        name="record_reconciliation",
    ),
    path(
        "charges/<int:pk>/provision/",
        _post(charges_views.update_provision),
        name="update_provision",
    ),
    path(
        "charges/<int:pk>/delete/",
        _post(charges_views.delete_reconciliation),
        name="delete_reconciliation",
    ),
    # Applications
    path("applications/", application_views.applications, name="applications"),
    path(
        "applications/new/",
        application_views.edit_application,
        name="new_application",
    ),
    path(
        "application/<int:pk>/",
        application_views.application_detail,
        name="application_detail",
    ),
    path(
        "application/<int:pk>/edit/",
        application_views.edit_application,
        name="edit_application",
    ),
    path(
        "application/<int:pk>/upload/",
        _post(application_views.upload_application_document),
        name="upload_application_document",
    ),
    path(
        "application/<int:pk>/status/",
        _post(application_views.set_application_status),
        name="set_application_status",
    ),
    path(
        "application/<int:pk>/accept/",
        application_views.accept_application,
        name="accept_application",
    ),
    path("lease/<int:lease_pk>/party/new/", views.edit_party, name="new_party"),
    path(
        "lease/<int:lease_pk>/party/<int:pk>/edit/",
        views.edit_party,
        name="edit_party",
    ),
    path(
        "lease/<int:lease_pk>/party/<int:pk>/delete/",
        _post(views.delete_party),
        name="delete_party",
    ),
]
