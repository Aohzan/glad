"""Views for the finance app."""

from .chart_views import chart_data
from .csv_views import csv_export, csv_export_synthesis, csv_import, csv_import_confirm
from .index_views import index
from .investment_views import (
    backfill_holding_history,
    create_investment,
    delete_holding_history,
    delete_investment,
    delete_investment_cash,
    delete_investment_deposit,
    delete_investment_holding,
    edit_holding_history,
    edit_investment,
    edit_investment_cash,
    edit_investment_deposit,
    edit_investment_holding,
    holding_detail,
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
    "backfill_holding_history",
    "chart_data",
    "create_investment",
    "create_saving",
    "csv_export",
    "csv_export_synthesis",
    "csv_import",
    "csv_import_confirm",
    "delete_holding_history",
    "delete_investment",
    "delete_investment_cash",
    "delete_investment_deposit",
    "delete_investment_holding",
    "delete_saving",
    "delete_saving_deposit",
    "delete_saving_value",
    "edit_holding_history",
    "edit_investment",
    "edit_investment_cash",
    "edit_investment_deposit",
    "edit_investment_holding",
    "edit_saving",
    "edit_saving_deposit",
    "edit_saving_value",
    "holding_detail",
    "index",
    "investment_detail",
    "saving_detail",
    "toggle_investment_favorite",
    "toggle_saving_favorite",
    "update_accounts",
]
