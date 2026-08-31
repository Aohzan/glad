"""URL configuration for the property app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    # Property
    path("", views.index, name="index"),
    path("new/", views.create_property, name="create"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.edit_property, name="edit"),
    path(
        "<int:pk>/favorite/",
        cast(Callable[..., HttpResponseBase], views.toggle_property_favorite),
        name="toggle_favorite",
    ),
    path("<int:pk>/loans/", views.manage_property_loans, name="loans"),
    path(
        "<int:pk>/loans/<int:loan_pk>/amortization/import/",
        cast(Callable[..., HttpResponseBase], views.import_loan_amortization),
        name="loan_amortization_import",
    ),
    path(
        "<int:pk>/loans/<int:loan_pk>/amortization/generate/",
        cast(Callable[..., HttpResponseBase], views.generate_loan_amortization),
        name="loan_amortization_generate",
    ),
    path(
        "<int:pk>/loans/<int:loan_pk>/amortization/clear/",
        cast(Callable[..., HttpResponseBase], views.clear_loan_amortization),
        name="loan_amortization_clear",
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
    path("lmnp_accounting/", views.accounting_lmnp_reel, name="lmnp_accounting"),
    # Income & expenses report
    path("report/", views.report_view, name="report"),
    # All loans dashboard
    path("loans/", views.all_loans_view, name="all_loans"),
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
    # API
    path(
        "<int:pk>/api/dashboard-card/",
        views.property_dashboard_card_api,
        name="api_dashboard_card",
    ),
    path(
        "scpi/<int:pk>/api/dashboard-card/",
        views.scpi_dashboard_card_api,
        name="api_scpi_dashboard_card",
    ),
    path(
        "api/address-autocomplete/",
        views.address_autocomplete_api,
        name="api_address_autocomplete",
    ),
    path(
        "<int:pk>/api/cadastral/",
        views.cadastral_lookup_api,
        name="api_cadastral_lookup",
    ),
    path(
        "<int:pk>/api/dvf-estimate/",
        views.property_dvf_estimate_api,
        name="api_dvf_estimate",
    ),
    # Async panel fragments
    path(
        "<int:pk>/panel/cashflow/", views.property_panel_cashflow, name="panel_cashflow"
    ),
    path(
        "<int:pk>/panel/projection/",
        views.property_panel_projection,
        name="panel_projection",
    ),
    path("<int:pk>/panel/balance/", views.property_panel_balance, name="panel_balance"),
    path("<int:pk>/panel/info/", views.property_panel_info, name="panel_info"),
    path("<int:pk>/panel/loans/", views.property_panel_loans, name="panel_loans"),
    path("<int:pk>/panel/leases/", views.property_panel_leases, name="panel_leases"),
    path("<int:pk>/panel/mandate/", views.property_panel_mandate, name="panel_mandate"),
    path(
        "<int:pk>/panel/amortization/",
        views.property_panel_amortization,
        name="panel_amortization",
    ),
    # SCPI
    path("scpi/", views.scpi_list, name="scpi_list"),
    path("scpi/new/", views.edit_scpi, name="scpi_new"),
    path(
        "scpi/dividend/batch/",
        views.batch_scpi_dividends,
        name="scpi_dividend_batch",
    ),
    path("scpi/<int:scpi_pk>/", views.scpi_fund_detail, name="scpi_fund_detail"),
    path("scpi/<int:scpi_pk>/edit/", views.edit_scpi, name="scpi_edit"),
    path("scpi/<int:scpi_pk>/delete/", views.delete_scpi, name="scpi_delete"),
    path(
        "scpi/<int:scpi_pk>/price/add/",
        views.add_scpi_share_price,
        name="scpi_share_price_add",
    ),
    path(
        "scpi/<int:scpi_pk>/price/<int:price_pk>/delete/",
        views.delete_scpi_share_price,
        name="scpi_share_price_delete",
    ),
    path(
        "scpi/investment/new/",
        views.edit_scpi_investment,
        name="scpi_investment_new",
    ),
    path(
        "scpi/investment/<int:investment_pk>/edit/",
        views.edit_scpi_investment,
        name="scpi_investment_edit",
    ),
    path(
        "scpi/investment/<int:investment_pk>/delete/",
        views.delete_scpi_investment,
        name="scpi_investment_delete",
    ),
    path(
        "scpi/<int:scpi_pk>/dividend/add/",
        views.edit_scpi_dividend,
        name="scpi_dividend_add",
    ),
    path(
        "scpi/<int:scpi_pk>/dividend/<int:dividend_pk>/edit/",
        views.edit_scpi_dividend,
        name="scpi_dividend_edit",
    ),
    path(
        "scpi/<int:scpi_pk>/dividend/<int:dividend_pk>/delete/",
        views.delete_scpi_dividend,
        name="scpi_dividend_delete",
    ),
    path(
        "scpi/investment/<int:investment_pk>/theoretical-value/add/",
        views.edit_scpi_theoretical_value,
        name="scpi_theoretical_value_add",
    ),
    path(
        "scpi/investment/<int:investment_pk>/theoretical-value/<int:value_pk>/edit/",
        views.edit_scpi_theoretical_value,
        name="scpi_theoretical_value_edit",
    ),
    path(
        "scpi/investment/<int:investment_pk>/theoretical-value/<int:value_pk>/delete/",
        views.delete_scpi_theoretical_value,
        name="scpi_theoretical_value_delete",
    ),
]
