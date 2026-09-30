"""Finance views."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from finance import views
from finance.views.api_views import (
    AccountsSummaryApiView,
    HoldingAutofillApiView,
    HoldingLiveInfoApiView,
    InvestmentLiveChangeApiView,
)

app_name = "finance"

urlpatterns = [
    # Main views
    path("", views.index, name="index"),
    path("update", views.update_accounts, name="update"),
    # Chart data
    path(
        "chart-data/<str:data_type>/<int:object_id>/",
        views.chart_data,
        name="chart_data",
    ),
    # CSV import/export
    path("csv/export", views.csv_export, name="csv_export"),
    path(
        "csv/export/synthesis", views.csv_export_synthesis, name="csv_export_synthesis"
    ),
    path("csv/import", views.csv_import, name="csv_import"),
    path("csv/import/confirm", views.csv_import_confirm, name="csv_import_confirm"),
    # API
    path(
        "api/accounts-summary/",
        AccountsSummaryApiView.as_view(),
        name="api_accounts_summary",
    ),
    path(
        "api/holding-autofill/",
        HoldingAutofillApiView.as_view(),
        name="api_holding_autofill",
    ),
    path(
        "api/investment/<int:account_pk>/holding/<int:holding_pk>/live-info/",
        HoldingLiveInfoApiView.as_view(),
        name="api_holding_live_info",
    ),
    path(
        "api/investments/live-change/",
        InvestmentLiveChangeApiView.as_view(),
        name="api_investments_live_change",
    ),
    # ─── Saving accounts ─────────────────────────────────────────────────────
    path("saving/new/", views.create_saving, name="new_saving"),
    path("saving/<int:pk>/", views.saving_detail, name="saving_detail"),
    path("saving/<int:pk>/edit/", views.edit_saving, name="edit_saving"),
    path("saving/<int:pk>/delete/", views.delete_saving, name="delete_saving"),
    path(
        "saving/<int:pk>/favorite/",
        cast(Callable[..., HttpResponseBase], views.toggle_saving_favorite),
        name="toggle_saving_favorite",
    ),
    # Saving values
    path(
        "saving/<int:account_pk>/value/new/",
        views.edit_saving_value,
        name="new_saving_value",
    ),
    path(
        "saving/<int:account_pk>/value/<int:value_pk>/edit/",
        views.edit_saving_value,
        name="edit_saving_value",
    ),
    path(
        "saving/<int:account_pk>/value/<int:value_pk>/delete/",
        views.delete_saving_value,
        name="delete_saving_value",
    ),
    # Saving deposits
    path(
        "saving/<int:account_pk>/deposit/new/",
        views.edit_saving_deposit,
        name="new_saving_deposit",
    ),
    path(
        "saving/<int:account_pk>/deposit/<int:deposit_pk>/edit/",
        views.edit_saving_deposit,
        name="edit_saving_deposit",
    ),
    path(
        "saving/<int:account_pk>/deposit/<int:deposit_pk>/delete/",
        views.delete_saving_deposit,
        name="delete_saving_deposit",
    ),
    # ─── Other assets ─────────────────────────────────────────────────────────
    path("other/", views.other_asset_list, name="other_asset_list"),
    path("other/new/", views.create_other_asset, name="new_other_asset"),
    path("other/<int:pk>/", views.other_asset_detail, name="other_asset_detail"),
    path("other/<int:pk>/edit/", views.edit_other_asset, name="edit_other_asset"),
    path(
        "other/<int:pk>/delete/",
        cast(Callable[..., HttpResponseBase], views.delete_other_asset),
        name="delete_other_asset",
    ),
    path(
        "other/<int:pk>/price/",
        cast(Callable[..., HttpResponseBase], views.update_other_asset_price),
        name="update_other_asset_price",
    ),
    path(
        "other/<int:asset_pk>/value/new/",
        views.edit_other_asset_value,
        name="new_other_asset_value",
    ),
    path(
        "other/<int:asset_pk>/value/<int:value_pk>/edit/",
        views.edit_other_asset_value,
        name="edit_other_asset_value",
    ),
    path(
        "other/<int:asset_pk>/value/<int:value_pk>/delete/",
        views.delete_other_asset_value,
        name="delete_other_asset_value",
    ),
    # ─── Investment accounts ──────────────────────────────────────────────────
    path("investment/new/", views.create_investment, name="new_investment"),
    path("investment/<int:pk>/", views.investment_detail, name="investment_detail"),
    path("investment/<int:pk>/edit/", views.edit_investment, name="edit_investment"),
    path(
        "investment/<int:pk>/delete/",
        views.delete_investment,
        name="delete_investment",
    ),
    path(
        "investment/<int:pk>/favorite/",
        cast(Callable[..., HttpResponseBase], views.toggle_investment_favorite),
        name="toggle_investment_favorite",
    ),
    # Holdings
    path(
        "investment/<int:account_pk>/holding/new/",
        views.edit_investment_holding,
        name="new_holding",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/",
        views.holding_detail,
        name="holding_detail",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/edit/",
        views.edit_investment_holding,
        name="edit_holding",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/delete/",
        views.delete_investment_holding,
        name="delete_holding",
    ),
    # Investment deposits
    path(
        "investment/<int:account_pk>/deposit/new/",
        views.edit_investment_deposit,
        name="new_investment_deposit",
    ),
    path(
        "investment/<int:account_pk>/deposit/<int:deposit_pk>/edit/",
        views.edit_investment_deposit,
        name="edit_investment_deposit",
    ),
    path(
        "investment/<int:account_pk>/deposit/<int:deposit_pk>/delete/",
        views.delete_investment_deposit,
        name="delete_investment_deposit",
    ),
    # Investment cash
    path(
        "investment/<int:account_pk>/cash/new/",
        views.edit_investment_cash,
        name="new_investment_cash",
    ),
    path(
        "investment/<int:account_pk>/cash/<int:cash_pk>/edit/",
        views.edit_investment_cash,
        name="edit_investment_cash",
    ),
    path(
        "investment/<int:account_pk>/cash/<int:cash_pk>/delete/",
        views.delete_investment_cash,
        name="delete_investment_cash",
    ),
    # Holding history
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/history/new/",
        views.edit_holding_history,
        name="new_holding_history",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/history/<int:history_pk>/edit/",
        views.edit_holding_history,
        name="edit_holding_history",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/history/<int:history_pk>/delete/",
        views.delete_holding_history,
        name="delete_holding_history",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/rate/new/",
        cast(Callable[..., HttpResponseBase], views.add_euro_fund_rate),
        name="add_euro_fund_rate",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/rate/<int:rate_pk>/delete/",
        cast(Callable[..., HttpResponseBase], views.delete_euro_fund_rate),
        name="delete_euro_fund_rate",
    ),
    path(
        "investment/<int:account_pk>/holding/<int:holding_pk>/history/backfill/",
        views.backfill_holding_history,
        name="backfill_holding_history",
    ),
]
