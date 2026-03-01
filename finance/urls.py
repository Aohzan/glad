"""Finance views."""

from django.urls import path

from finance import views

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
    path("csv/import", views.csv_import, name="csv_import"),
    path("csv/import/confirm", views.csv_import_confirm, name="csv_import_confirm"),
]
