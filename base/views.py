"""Base views for the Django application."""

import datetime
from typing import Any

from django.contrib import messages
from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from property.models import Property
from property.models.scpi import SCPI


def get_object_or_redirect(
    request: HttpRequest,
    model: type[models.Model],
    pk: int,
    error_message: str,
    redirect_url: str,
    redirect_kwargs: dict[str, Any] | None = None,
    **filter_kwargs: Any,
) -> tuple[models.Model | None, HttpResponse | None]:
    """Retrieve a model instance or redirect with an error message.

    Returns ``(obj, None)`` on success and ``(None, redirect_response)`` when
    the object is not found.  Any extra *filter_kwargs* are passed directly to
    the ORM ``filter()`` call alongside the ``pk`` lookup so callers can scope
    the query (e.g. ``property=property_obj``).  *redirect_kwargs* are forwarded
    to ``redirect()`` as keyword arguments (e.g. ``{"pk": property_pk}``).
    """
    obj = model.objects.filter(pk=pk, **filter_kwargs).first()
    if obj is not None:
        return obj, None
    messages.error(request, error_message)
    return None, redirect(redirect_url, **(redirect_kwargs or {}))


# Helper function to convert datetime to date if needed
def safe_date_compare(date_obj, datetime_obj):
    """
    Safely compare a date and datetime object by converting datetime to date.
    This avoids the '<' not supported between instances of 'datetime.date' and 'datetime.datetime' error.
    """
    if isinstance(date_obj, datetime.datetime) and isinstance(
        datetime_obj, datetime.date
    ):
        return date_obj.date() <= datetime_obj
    elif isinstance(date_obj, datetime.date) and isinstance(
        datetime_obj, datetime.datetime
    ):
        return date_obj <= datetime_obj.date()
    else:
        return date_obj <= datetime_obj


class IndexView(TemplateView):
    """View for the index page — shells out to async API endpoints."""

    template_name = "index.html"

    def get(self, request, *args, **kwargs):
        property_pks = list(
            Property.objects.filter(is_active=True)
            .order_by("-is_favorite", "name")
            .values_list("pk", flat=True)
        )
        scpi_pks = list(SCPI.objects.order_by("name").values_list("pk", flat=True))
        return render(
            request,
            self.template_name,
            {
                "property_pks": property_pks,
                "scpi_pks": scpi_pks,
            },
        )


def healthcheck(request):
    """Handle GET requests for health check."""
    return JsonResponse({"status": "OK"}, status=200)


def error_400(request, exception=None):
    """Render the 400 Bad Request error page."""
    return render(request, "400.html", status=400)


def error_403(request, exception=None):
    """Render the 403 Forbidden error page."""
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    """Render the 404 Not Found error page."""
    return render(request, "404.html", status=404)


def error_500(request):
    """Render the 500 Internal Server Error page."""
    return render(request, "500.html", status=500)
