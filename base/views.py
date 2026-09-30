"""Base views for the Django application."""

import datetime
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.staticfiles.storage import staticfiles_storage
from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from base.models import EconomicIndex
from base.services.deadlines import upcoming_deadlines
from base.services.insee import InseeError, refresh_index
from property.models import Property
from property.models.scpi import SCPI
from property.services.checks import pending_checks_summary


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


DASHBOARD_DEADLINES = 8


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
                "property_checks": pending_checks_summary() if property_pks else None,
                "deadlines": upcoming_deadlines(limit=DASHBOARD_DEADLINES),
            },
        )


@require_POST  # type: ignore
def refresh_economic_indices(request: HttpRequest) -> HttpResponse:
    """Download the latest INSEE index values, then go back to the ``next`` page."""
    try:
        for index in EconomicIndex:
            refresh_index(index)
    except InseeError:
        messages.error(request, _("Could not download the INSEE indices."))
    else:
        messages.success(request, _("INSEE indices updated."))
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("index")
    return redirect(next_url)


@login_not_required
def favicon(request):
    """Redirect the browser's implicit /favicon.ico lookup to the static file.

    Browsers request the icon at the site root whatever the ``<link rel="icon">``
    says, and without this route every one of them raises a ``Resolver404``.
    """
    return redirect(staticfiles_storage.url("favicon.ico"), permanent=True)


@login_not_required
def healthcheck(request):
    """Handle GET requests for health check (no authentication required)."""
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
