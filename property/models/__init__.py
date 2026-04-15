"""Property models package — re-exports all models for backward-compatible imports."""

from property.models.asset import Property, PropertyLoan, PropertyValue
from property.models.lease import Lease, LeaseTenant, Tenant
from property.models.ledger import PropertyLedgerEntry
from property.models.management import ManagementMandate, PropertyManager

__all__ = [
    "Property",
    "PropertyLoan",
    "PropertyValue",
    "Tenant",
    "Lease",
    "LeaseTenant",
    "PropertyManager",
    "ManagementMandate",
    "PropertyLedgerEntry",
]
