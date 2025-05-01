"""Glad URL Configuration"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("base.urls")),
    path("finance/", include("finance.urls")),
    path("property/", include("property.urls")),
    path("admin/", admin.site.urls),
]
