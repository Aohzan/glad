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
from property.models.scpi import (
    SCPI,
    SCPIBareOwnershipTheoreticalValue,
    SCPIDividend,
    SCPIInvestment,
    SCPISharePrice,
)

__all__ = [
    "SCPI",
    "AmortizationAsset",
    "AmortizationSetup",
    "Lease",
    "ManagementCategory",
    "ManagementMandate",
    "Property",
    "PropertyLedgerEntry",
    "PropertyLedgerEntryException",
    "PropertyLoan",
    "PropertyLoanAmortizationEntry",
    "PropertyValue",
    "SCPIBareOwnershipTheoreticalValue",
    "SCPIDividend",
    "SCPIInvestment",
    "SCPISharePrice",
]
