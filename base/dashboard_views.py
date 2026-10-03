"""Dashboard page and the fragments it loads asynchronously."""

import datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from base.services import dashboard
from base.services.operations import recent_operations
from property.models import Property
from property.services.checks import pending_checks_summary

RECENT_OPERATIONS = 5


def index(request: HttpRequest) -> HttpResponse:
    """Dashboard shell; the figures are loaded by the panels below."""
    has_properties = Property.objects.filter(is_active=True).exists()
    return render(
        request,
        "index.html",
        {
            "property_checks": pending_checks_summary() if has_properties else None,
            "dashboard_i18n": {
                "net": str(_("Net")),
                "gross": str(_("Gross")),
                "debt": str(_("Debts")),
                "error": str(_("Could not load chart data.")),
            },
        },
    )


def panel_overview(request: HttpRequest) -> HttpResponse:
    """Hero card, allocation strip, asset registry and watch list."""
    today = datetime.date.today()
    currency = dashboard.default_currency()
    groups = dashboard.registry(currency, today)
    hero = dashboard.hero_summary(groups, currency, today)
    rows = [r for g in groups for r in g.rows]
    holders = sorted({r.holder for r in rows})
    return render(
        request,
        "dashboard/_overview.html",
        {
            "currency": currency,
            "hero": hero,
            "groups": groups,
            "holders": holders,
            "asset_count": len(rows),
            "max_value": max((r.value for r in rows), default=0),
            "watch": dashboard.watch_items(groups, today),
            "operations": recent_operations(RECENT_OPERATIONS),
        },
    )


def panel_property(request: HttpRequest) -> HttpResponse:
    """Liabilities and median monthly flows of the properties."""
    today = datetime.date.today()
    loans = dashboard.liabilities(today)
    flows = dashboard.property_flows(today)
    return render(
        request,
        "dashboard/_property.html",
        {
            "currency": dashboard.default_currency(),
            "loans": loans,
            "loans_total": sum(loan.remaining for loan in loans),
            "loans_monthly": sum(loan.monthly for loan in loans),
            "flows": flows,
            "flows_total": {
                "rents": sum(f.rents for f in flows),
                "charges": sum(f.charges for f in flows),
                "loan": sum(f.loan for f in flows),
                "cashflow": sum(f.cashflow for f in flows),
            },
        },
    )
