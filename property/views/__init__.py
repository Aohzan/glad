"""Views for the property app — re-exported from sub-modules."""

from property.views.api_views import (
    AddressAutocompleteApiView,
    CadastralLookupApiView,
    PropertyDashboardCardApiView,
    PropertyDvfEstimateApiView,
    SCPIDashboardCardApiView,
)
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
from property.views.loans_views import all_loans_view

property_dashboard_card_api = PropertyDashboardCardApiView.as_view()
scpi_dashboard_card_api = SCPIDashboardCardApiView.as_view()
address_autocomplete_api = AddressAutocompleteApiView.as_view()
cadastral_lookup_api = CadastralLookupApiView.as_view()
property_dvf_estimate_api = PropertyDvfEstimateApiView.as_view()

# SCPI views
from property.views.scpi_views import (
    add_scpi_share_price,
    batch_scpi_dividends,
    delete_scpi,
    delete_scpi_dividend,
    delete_scpi_investment,
    delete_scpi_share_price,
    delete_scpi_theoretical_value,
    edit_scpi,
    edit_scpi_dividend,
    edit_scpi_investment,
    edit_scpi_theoretical_value,
    scpi_fund_detail,
    scpi_list,
)

__all__ = [
    "PropertyDetailView",
    "accounting_lmnp_reel",
    "add_scpi_share_price",
    "address_autocomplete_api",
    "all_loans_view",
    "batch_scpi_dividends",
    "cadastral_lookup_api",
    "clear_loan_amortization",
    "create_amortization_asset",
    "create_property",
    "csv_import",
    "csv_import_confirm",
    "delete_amortization_asset",
    "delete_lease",
    "delete_ledger_entry",
    "delete_ledger_entry_occurrence",
    "delete_mandate",
    "delete_property_valuation",
    "delete_scpi",
    "delete_scpi_dividend",
    "delete_scpi_investment",
    "delete_scpi_share_price",
    "delete_scpi_theoretical_value",
    "edit_amortization_asset",
    "edit_lease",
    "edit_ledger_entry",
    "edit_ledger_entry_occurrence",
    "edit_mandate",
    "edit_property",
    "edit_scpi",
    "edit_scpi_dividend",
    "edit_scpi_investment",
    "edit_scpi_theoretical_value",
    "generate_loan_amortization",
    "import_loan_amortization",
    "index",
    "initialize_amortization",
    "manage_property_loans",
    "property_dashboard_card_api",
    "property_dvf_estimate_api",
    "property_panel_amortization",
    "property_panel_balance",
    "property_panel_cashflow",
    "property_panel_info",
    "property_panel_leases",
    "property_panel_loans",
    "property_panel_mandate",
    "property_panel_projection",
    "report_view",
    "scpi_dashboard_card_api",
    "scpi_fund_detail",
    "scpi_list",
    "toggle_property_favorite",
]
