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
    # Loan annual statements (bank-provided interest/insurance)
    path(
        "<int:property_pk>/loans/<int:loan_pk>/statement/new/",
        views.edit_loan_annual_statement,
        name="new_loan_statement",
    ),
    path(
        "<int:property_pk>/loans/<int:loan_pk>/statement/<int:statement_pk>/edit/",
        views.edit_loan_annual_statement,
        name="edit_loan_statement",
    ),
    path(
        "<int:property_pk>/loans/<int:loan_pk>/statement/<int:statement_pk>/delete/",
        views.delete_loan_annual_statement,
        name="delete_loan_statement",
    ),
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
    path(
        "<int:property_pk>/entry/<int:entry_pk>/occurrence/<str:occurrence_date>/edit/",
        views.edit_ledger_entry_occurrence,
        name="edit_entry_occurrence",
    ),
    path(
        "<int:property_pk>/entry/<int:entry_pk>/occurrence/<str:occurrence_date>/delete/",
        views.delete_ledger_entry_occurrence,
        name="delete_entry_occurrence",
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
    # CSV import for ledger entries
    path(
        "<int:property_pk>/csv/import/",
        views.csv_import,
        name="csv_import",
    ),
    path(
        "<int:property_pk>/csv/import/confirm/",
        views.csv_import_confirm,
        name="csv_import_confirm",
    ),
    # Accounting dashboard (all LMNP réel properties)
    path("accounting/", views.accounting_lmnp_reel, name="accounting"),
    # Income & expenses report
    path("report/", views.report_view, name="report"),
    # Amortization initialization
    path(
        "<int:pk>/amortization/initialize/",
        views.initialize_amortization,
        name="initialize_amortization",
    ),
    # Amortization assets (immobilisations)
    path(
        "<int:property_pk>/amortization/new/",
        views.create_amortization_asset,
        name="new_amortization",
    ),
    path(
        "<int:property_pk>/amortization/<int:asset_pk>/edit/",
        views.edit_amortization_asset,
        name="edit_amortization",
    ),
    path(
        "<int:property_pk>/amortization/<int:asset_pk>/delete/",
        views.delete_amortization_asset,
        name="delete_amortization",
    ),
]
