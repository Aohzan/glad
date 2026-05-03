"""Views for the property app — re-exported from sub-modules."""

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
from property.views.detail_views import PropertyDetailView
from property.views.edit_views import (
    create_property,
    edit_property,
    manage_property_loans,
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

__all__ = [
    "index",
    "PropertyDetailView",
    "edit_property",
    "create_property",
    "manage_property_loans",
    "delete_property_valuation",
    "edit_ledger_entry",
    "delete_ledger_entry",
    "edit_ledger_entry_occurrence",
    "delete_ledger_entry_occurrence",
    "edit_lease",
    "delete_lease",
    "edit_mandate",
    "delete_mandate",
    "accounting_lmnp_reel",
    "report_view",
    "initialize_amortization",
    "create_amortization_asset",
    "edit_amortization_asset",
    "delete_amortization_asset",
    "csv_import",
    "csv_import_confirm",
]
