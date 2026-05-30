"""URL configuration for the base app."""

from django.urls import path

from base import api_views, views

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("health", views.healthcheck),
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
]
