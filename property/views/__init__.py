"""Views for the property app — re-exported from sub-modules."""

from property.views.crud_views import (
    delete_lease,
    delete_ledger_entry,
    delete_mandate,
    delete_property_valuation,
    delete_tenant,
    edit_lease,
    edit_ledger_entry,
    edit_manager,
    edit_mandate,
    edit_tenant,
)
from property.views.detail_views import PropertyDetailView
from property.views.edit_views import edit_property
from property.views.index_views import index

__all__ = [
    "index",
    "PropertyDetailView",
    "edit_property",
    "delete_property_valuation",
    "edit_ledger_entry",
    "delete_ledger_entry",
    "edit_tenant",
    "delete_tenant",
    "edit_lease",
    "delete_lease",
    "edit_manager",
    "edit_mandate",
    "delete_mandate",
]
