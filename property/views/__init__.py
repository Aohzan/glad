"""Views for the property app — re-exported from sub-modules."""

from property.views.api_views import PropertyDashboardCardApiView
from property.views.crud_views import (
    delete_lease,
    delete_ledger_entry,
    delete_ledger_entry_occurrence,
    delete_mandate,
    delete_property_valuation,
    edit_lease,
    edit_ledger_entry,
    edit_ledger_entry_occurrence,
    edit_mandate,
)
from property.views.csv_views import csv_import, csv_import_confirm
from property.views.detail_views import (
    PropertyDetailView,
    property_panel_amortization,
    property_panel_balance,
    property_panel_cashflow,
    property_panel_info,
    property_panel_leases,
    property_panel_loans,
    property_panel_mandate,
    property_panel_projection,
)
from property.views.edit_views import (
    clear_loan_amortization,
    create_property,
    edit_property,
    generate_loan_amortization,
    import_loan_amortization,
    manage_property_loans,
    toggle_property_favorite,
)
from property.views.fiscal_views import (
    accounting_lmnp_reel,
    create_amortization_asset,
    delete_amortization_asset,
    edit_amortization_asset,
    initialize_amortization,
    report_view,
)
from property.views.index_views import index

property_dashboard_card_api = PropertyDashboardCardApiView.as_view()

__all__ = [
    "index",
    "PropertyDetailView",
    "edit_property",
    "create_property",
    "manage_property_loans",
    "import_loan_amortization",
    "generate_loan_amortization",
    "clear_loan_amortization",
    "delete_property_valuation",
    "edit_ledger_entry",
    "delete_ledger_entry",
    "edit_ledger_entry_occurrence",
    "delete_ledger_entry_occurrence",
    "edit_lease",
    "delete_lease",
    "edit_mandate",
    "delete_mandate",
    "toggle_property_favorite",
    "accounting_lmnp_reel",
    "report_view",
    "initialize_amortization",
    "create_amortization_asset",
    "edit_amortization_asset",
    "delete_amortization_asset",
    "csv_import",
    "csv_import_confirm",
    "property_dashboard_card_api",
    "property_panel_cashflow",
    "property_panel_projection",
    "property_panel_balance",
    "property_panel_info",
    "property_panel_loans",
    "property_panel_leases",
    "property_panel_mandate",
    "property_panel_amortization",
]
