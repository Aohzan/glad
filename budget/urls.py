"""URL configuration for the budget app."""

from collections.abc import Callable
from typing import cast

from django.http import HttpResponseBase
from django.urls import path

from budget import views

app_name = "budget"


def _post(view) -> Callable[..., HttpResponseBase]:
    return cast(Callable[..., HttpResponseBase], view)


urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.year_create, name="year_new"),
    path("categories/", views.category_list, name="categories"),
    path("categories/new/", views.category_create, name="category_new"),
    path(
        "categories/defaults/",
        _post(views.category_defaults),
        name="category_defaults",
    ),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path(
        "categories/<int:pk>/delete/",
        _post(views.category_delete),
        name="category_delete",
    ),
    path("lines/<int:pk>/edit/", views.line_edit, name="line_edit"),
    path("lines/<int:pk>/delete/", _post(views.line_delete), name="line_delete"),
    path("<int:year>/", views.year_detail, name="year"),
    path("<int:year>/edit/", views.year_edit, name="year_edit"),
    path("<int:year>/delete/", _post(views.year_delete), name="year_delete"),
    path("<int:year>/copy/", views.year_copy, name="year_copy"),
    path("<int:year>/lines/new/", views.line_create, name="line_new"),
    path("<int:year>/export/", views.csv_export, name="export"),
    path("<int:year>/import/", views.csv_import, name="import"),
    path(
        "<int:year>/import/confirm/",
        _post(views.csv_import_confirm),
        name="import_confirm",
    ),
    path("<int:year>/ai-prompt/", views.prompt, name="ai_prompt"),
]
