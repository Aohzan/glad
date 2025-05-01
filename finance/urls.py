"""Finance views."""

from django.urls import path

from finance import views

app_name = "finance"

urlpatterns = [
    # Main views
    path("", views.IndexView.as_view(), name="index"),
]
