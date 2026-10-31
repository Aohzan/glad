"""Automatic price update of the holdings, managed from one page."""

import json

from django.db.models import Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from finance.jobs import live_data_allowed, live_updatable_holdings
from finance.models.investment_account import InvestmentAccountHolding


def live_prices(request: HttpRequest) -> HttpResponse:
    """List the holdings with an ISIN and whether their price is updated every day.

    Each holding carries its last valuation date in ``last_valuation``.
    """
    holdings = (
        live_updatable_holdings()
        .select_related("account", "account__account_type")
        .annotate(last_valuation=Max("investmentaccountholdinghistory__valuation_date"))
    )
    return render(
        request,
        "finance/live_prices.html",
        {"holdings": holdings, "live_data_allowed": live_data_allowed()},
    )


@require_POST  # type: ignore
def toggle_holding_auto_update(
    request: HttpRequest, account_pk: int, holding_pk: int
) -> JsonResponse:
    """Set ``auto_update_price`` of a holding from a JSON body ``{"enabled": bool}``."""
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account_id=account_pk
    )
    try:
        enabled = json.loads(request.body or "{}").get("enabled")
    except json.JSONDecodeError, AttributeError:
        enabled = None
    if not isinstance(enabled, bool):
        return JsonResponse({"error": "invalid_request"}, status=400)
    if enabled and not holding.isin:
        # The daily job looks the price up by ISIN.
        return JsonResponse({"error": "no_isin"}, status=400)
    holding.auto_update_price = enabled
    holding.save(update_fields=["auto_update_price"])
    return JsonResponse({"auto_update_price": holding.auto_update_price})
