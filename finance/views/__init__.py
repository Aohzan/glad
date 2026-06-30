"""Views for the finance app."""

from .chart_views import chart_data
from .csv_views import csv_export, csv_export_synthesis, csv_import, csv_import_confirm
from .index_views import index
from .investment_views import (
    create_investment,
    delete_holding_history,
    delete_investment,
    delete_investment_deposit,
    delete_investment_holding,
    edit_holding_history,
    edit_investment,
    edit_investment_deposit,
    edit_investment_holding,
    investment_detail,
    toggle_investment_favorite,
)
from .saving_views import (
    create_saving,
    delete_saving,
    delete_saving_deposit,
    delete_saving_value,
    edit_saving,
    edit_saving_deposit,
    edit_saving_value,
    saving_detail,
    toggle_saving_favorite,
)
from .update_views import update_accounts

__all__ = [
    "index",
    "update_accounts",
    "chart_data",
    "csv_export",
    "csv_export_synthesis",
    "csv_import",
    "csv_import_confirm",
    "saving_detail",
    "create_saving",
    "edit_saving",
    "delete_saving",
    "edit_saving_value",
    "delete_saving_value",
    "edit_saving_deposit",
    "delete_saving_deposit",
    "investment_detail",
    "create_investment",
    "edit_investment",
    "delete_investment",
    "edit_investment_holding",
    "delete_investment_holding",
    "edit_investment_deposit",
    "delete_investment_deposit",
    "edit_holding_history",
    "delete_holding_history",
    "toggle_saving_favorite",
    "toggle_investment_favorite",
]
