"""URL configuration for the property app."""

from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.edit_property, name="edit"),
    path(
        "<int:property_pk>/valuation/<int:valuation_pk>/delete/",
        views.delete_property_valuation,
        name="delete_valuation",
    ),
    path(
        "<int:property_pk>/expense/<int:expense_pk>/edit/",
        views.edit_property_expense,
        name="edit_expense",
    ),
    path(
        "<int:property_pk>/expense/<int:expense_pk>/delete/",
        views.delete_property_expense,
        name="delete_expense",
    ),
    path(
        "<int:property_pk>/revenue/<int:revenue_pk>/edit/",
        views.edit_property_revenue,
        name="edit_revenue",
    ),
    path(
        "<int:property_pk>/revenue/<int:revenue_pk>/delete/",
        views.delete_property_revenue,
        name="delete_revenue",
    ),
]
