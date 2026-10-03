"""Tracking pages: upcoming deadlines and the history of operations."""

import datetime

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from base.services.deadlines import upcoming_deadlines
from base.services.operations import OPERATION_KINDS, operations_queryset, resolve

OPERATIONS_PER_PAGE = 50

#: Filters of the operations page: key, label and kinds of operation.
OPERATION_FILTERS = {
    "valuations": (
        _("Valuations"),
        [k for k, spec in OPERATION_KINDS.items() if spec.flow == "value"],
    ),
    "deposits": (_("Deposits"), ["saving_deposit", "investment_deposit"]),
    "dividends": (_("Dividends"), ["scpi_dividend"]),
}


def deadlines(request: HttpRequest) -> HttpResponse:
    """Every deadline from the last 30 days to the next 12 months, by month."""
    today = datetime.date.today()
    items = upcoming_deadlines(today)
    upcoming = [d for d in items if d.days_left >= 0]
    past = [d for d in items if d.days_left < 0]
    past.reverse()
    return render(
        request,
        "deadlines.html",
        {"upcoming": upcoming, "past": past, "today": today},
    )


def operations(request: HttpRequest) -> HttpResponse:
    """Paginated history of the operations, optionally of one kind."""
    kind = request.GET.get("kind", "")
    if kind not in OPERATION_FILTERS:
        kind = ""
    kinds = OPERATION_FILTERS[kind][1] if kind else None
    paginator = Paginator(operations_queryset(kinds), OPERATIONS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "operations.html",
        {
            "page": page,
            "operations": resolve(page.object_list),
            "kind": kind,
            "filters": [
                (key, label) for key, (label, _kinds) in OPERATION_FILTERS.items()
            ],
        },
    )
