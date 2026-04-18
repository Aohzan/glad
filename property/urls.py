"""URL configuration for the property app."""

from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    # Property
    path("", views.index, name="index"),
    path("new/", views.create_property, name="create"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.edit_property, name="edit"),
    path("<int:pk>/loans/", views.manage_property_loans, name="loans"),
    # Property valuation
    path(
        "<int:property_pk>/valuation/<int:valuation_pk>/delete/",
        views.delete_property_valuation,
        name="delete_valuation",
    ),
    # Ledger entries (unified income + expense)
    path(
        "<int:property_pk>/entry/<int:entry_pk>/edit/",
        views.edit_ledger_entry,
        name="edit_entry",
    ),
    path(
        "<int:property_pk>/entry/<int:entry_pk>/delete/",
        views.delete_ledger_entry,
        name="delete_entry",
    ),
    # Leases
    path("<int:property_pk>/lease/new/", views.edit_lease, name="new_lease"),
    path(
        "<int:property_pk>/lease/<int:lease_pk>/edit/",
        views.edit_lease,
        name="edit_lease",
    ),
    path(
        "<int:property_pk>/lease/<int:lease_pk>/delete/",
        views.delete_lease,
        name="delete_lease",
    ),
    # Mandates
    path("<int:property_pk>/mandate/new/", views.edit_mandate, name="new_mandate"),
    path(
        "<int:property_pk>/mandate/<int:mandate_pk>/edit/",
        views.edit_mandate,
        name="edit_mandate",
    ),
    path(
        "<int:property_pk>/mandate/<int:mandate_pk>/delete/",
        views.delete_mandate,
        name="delete_mandate",
    ),
]
