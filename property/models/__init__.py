"""Property models package — re-exports all models for backward-compatible imports."""

from property.models.asset import (
    AmortizationAsset,
    AmortizationSetup,
    Property,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
    PropertyValue,
)
from property.models.lease import Lease
from property.models.ledger import (
    ManagementCategory,
    PropertyLedgerEntry,
    PropertyLedgerEntryException,
)
from property.models.management import ManagementMandate
from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment, SCPISharePrice

__all__ = [
    "AmortizationAsset",
    "AmortizationSetup",
    "Property",
    "PropertyLoan",
    "PropertyLoanAmortizationEntry",
    "PropertyValue",
    "Lease",
    "ManagementCategory",
    "ManagementMandate",
    "PropertyLedgerEntry",
    "PropertyLedgerEntryException",
    "SCPI",
    "SCPIDividend",
    "SCPIInvestment",
    "SCPISharePrice",
]
