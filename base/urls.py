"""URL configuration for the base app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from base import (
    api_views,
    dashboard_views,
    ownership_views,
    search_views,
    tracking_views,
    views,
)

urlpatterns = [
    path("", dashboard_views.index, name="index"),
    path(
        "dashboard/panel/overview/",
        dashboard_views.panel_overview,
        name="dashboard_panel_overview",
    ),
    path(
        "dashboard/panel/property/",
        dashboard_views.panel_property,
        name="dashboard_panel_property",
    ),
    path("allocation/", views.allocation, name="allocation"),
    path("owners/", ownership_views.owners_overview, name="owners"),
    path("deadlines/", tracking_views.deadlines, name="deadlines"),
    path("operations/", tracking_views.operations, name="operations"),
    path("api/search/", search_views.api_search, name="api_search"),
    path(
        "owners/remove/<int:pk>/",
        cast(Callable[..., HttpResponseBase], ownership_views.delete_ownership),
        name="delete_ownership",
    ),
    path(
        "owners/<str:kind>/<int:pk>/",
        ownership_views.manage_owners,
        name="manage_owners",
    ),
    path("health", views.healthcheck),
    path("favicon.ico", views.favicon),
    path("api/net-worth/", api_views.NetWorthApiView.as_view(), name="api_net_worth"),
    path(
        "api/patrimony-chart/",
        api_views.PatrimonyChartApiView.as_view(),
        name="api_patrimony_chart",
    ),
    path(
        "api/recent-operations/",
        api_views.RecentOperationsApiView.as_view(),
        name="api_recent_operations",
    ),
    path("api/alerts/", api_views.AlertsApiView.as_view(), name="api_alerts"),
    path(
        "indices/refresh/",
        cast(Callable[..., HttpResponseBase], views.refresh_economic_indices),
        name="refresh_economic_indices",
    ),
]
