"""Views for the finance app - imports from views directory."""

# Import all views from the views directory
# Import Django functions and models for backward compatibility with tests
from django.shortcuts import render

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount
from finance.views.chart_views import chart_data
from finance.views.csv_views import (
    csv_export,
    csv_export_synthesis,
    csv_import,
    csv_import_confirm,
)
from finance.views.index_views import index
from finance.views.update_views import update_accounts

# Maintain backward compatibility by exposing all views at module level
__all__ = [
    "index",
    "update_accounts",
    "chart_data",
    "csv_export",
    "csv_export_synthesis",
    "csv_import",
    "csv_import_confirm",
    "render",  # For test mocking
    "SavingAccount",  # For test mocking
    "InvestmentAccount",  # For test mocking
]
