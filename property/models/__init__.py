"""Property models package — re-exports all models for backward-compatible imports."""

from property.models.asset import (
    AmortizationAsset,
    AmortizationSetup,
    Property,
    PropertyLoan,
    PropertyLoanAnnualStatement,
    PropertyLoanSchedule,
    PropertyValue,
)
from property.models.lease import Lease
from property.models.ledger import PropertyLedgerEntry, PropertyLedgerEntryException
from property.models.management import ManagementMandate

__all__ = [
    "AmortizationAsset",
    "AmortizationSetup",
    "Property",
    "PropertyLoan",
    "PropertyLoanAnnualStatement",
    "PropertyLoanSchedule",
    "PropertyValue",
    "Lease",
    "ManagementMandate",
    "PropertyLedgerEntry",
    "PropertyLedgerEntryException",
]
