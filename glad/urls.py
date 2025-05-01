"""Glad URL Configuration"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("base.urls")),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("finance/", include(("finance.urls", "finance"), namespace="finance")),
    path("property/", include(("property.urls", "property"), namespace="property")),
    path("admin/", admin.site.urls),
]
