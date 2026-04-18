"""Views for the property app — re-exported from sub-modules."""

from property.views.crud_views import (
    delete_lease,
    delete_ledger_entry,
    delete_mandate,
    delete_property_valuation,
    edit_lease,
    edit_ledger_entry,
    edit_mandate,
)
from property.views.detail_views import PropertyDetailView
from property.views.edit_views import (
    create_property,
    edit_property,
    manage_property_loans,
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
    "edit_lease",
    "delete_lease",
    "edit_mandate",
    "delete_mandate",
]
