"""API views for the finance app — JSON endpoints for the dashboard."""

import re
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
)
from finance.models.saving_account import SavingAccount
from finance.services.market_data import (
    MarketDataError,
    fetch_holding_autofill,
    get_live_quote,
)

_ISIN_RE = re.compile(r"^[A-Z0-9]{12}$")


@method_decorator(login_required, name="dispatch")
class AccountsSummaryApiView(View):
    """Return accounts breakdown, progress bars, and alerts for the dashboard."""

    def get(self, request):
        days = 30
        saving_accounts = SavingAccount.objects.filter(is_active=True).order_by(
            "-is_favorite", "name"
        )
        investment_accounts = InvestmentAccount.objects.filter(is_active=True).order_by(
            "-is_favorite", "name"
        )

        # Breakdown (donut chart)
        total_savings = sum((float(a.get_value().amount) for a in saving_accounts), 0.0)
        total_investments = sum(
            (float(a.current_value.amount) for a in investment_accounts), 0.0
        )
        breakdown_labels = ["Investments", "Savings"]
        breakdown_values = [total_investments, total_savings]

        # Per-account progress bars
        accounts = []
        for account in saving_accounts:
            prog = account.get_progression(days)
            accounts.append(
                {
                    "pk": account.pk,
                    "detail_url": reverse(
                        "finance:saving_detail", kwargs={"pk": account.pk}
                    ),
                    "name": str(account),
                    "value": float(account.get_value().amount),
                    "progression": float(prog.gross_progression),
                    "progression_percent": min(
                        max(float(prog.gross_progression), 0), 100
                    ),
                    "progression_css": (
                        "success"
                        if prog.gross_progression > 0
                        else "danger"
                        if prog.gross_progression < 0
                        else "secondary"
                    ),
                    "icon": "bi-piggy-bank",
                    "type": "savings",
                    "owner": account.owner or "",
                    "is_favorite": account.is_favorite,
                }
            )

        for account in investment_accounts:
            prog = account.get_progression(days)
            accounts.append(
                {
                    "pk": account.pk,
                    "detail_url": reverse(
                        "finance:investment_detail", kwargs={"pk": account.pk}
                    ),
                    "name": str(account),
                    "value": float(account.current_value.amount),
                    "progression": float(prog.gross_progression),
                    "progression_percent": min(
                        max(float(prog.gross_progression), 0), 100
                    ),
                    "progression_css": (
                        "success"
                        if prog.gross_progression > 0
                        else "danger"
                        if prog.gross_progression < 0
                        else "secondary"
                    ),
                    "icon": "bi-bar-chart-line",
                    "type": "investment",
                    "owner": account.owner or "",
                    "is_favorite": account.is_favorite,
                }
            )

        # Alerts
        alerts = []
        for account in saving_accounts:
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )
        for account in investment_accounts:
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )

        return JsonResponse(
            {
                "breakdown_labels": breakdown_labels,
                "breakdown_values": breakdown_values,
                "accounts": accounts,
                "alerts": alerts,
            }
        )


@method_decorator(login_required, name="dispatch")
class HoldingLiveInfoApiView(View):
    """Return a live market quote for a holding, resolved from its ISIN."""

    def get(self, request, account_pk, holding_pk):
        if not getattr(request.user.profile, "live_data_enabled", True):
            return JsonResponse({"error": "live_data_disabled"}, status=403)

        holding = get_object_or_404(
            InvestmentAccountHolding, pk=holding_pk, account_id=account_pk
        )
        if not holding.isin:
            return JsonResponse({"error": "no_isin"}, status=400)

        force = request.GET.get("force") == "1"
        try:
            quote = get_live_quote(holding.isin, force_refresh=force)
        except MarketDataError as exc:
            return JsonResponse({"error": str(exc)}, status=502)

        quantity = holding.quantity
        total_value = quote.price * quantity if quantity else None
        currency_mismatch = quote.currency != holding.account.currency

        return JsonResponse(
            {
                "name": quote.name,
                "price": float(quote.price),
                "currency": quote.currency,
                "previous_close": float(quote.previous_close)
                if quote.previous_close is not None
                else None,
                "day_high": float(quote.day_high)
                if quote.day_high is not None
                else None,
                "day_low": float(quote.day_low) if quote.day_low is not None else None,
                "year_high": float(quote.year_high)
                if quote.year_high is not None
                else None,
                "year_low": float(quote.year_low)
                if quote.year_low is not None
                else None,
                "fifty_day_average": float(quote.fifty_day_average)
                if quote.fifty_day_average is not None
                else None,
                "two_hundred_day_average": float(quote.two_hundred_day_average)
                if quote.two_hundred_day_average is not None
                else None,
                "exchange": quote.exchange,
                "as_of": quote.as_of.isoformat(),
                "quantity": float(quantity) if quantity is not None else None,
                "total_value": float(total_value) if total_value is not None else None,
                "account_currency": holding.account.currency,
                "currency_mismatch": currency_mismatch,
            }
        )


@method_decorator(login_required, name="dispatch")
class HoldingAutofillApiView(View):
    """Return holding metadata (code, name, issuer, fees, price) from an ISIN."""

    def get(self, request):
        if not getattr(request.user.profile, "live_data_enabled", True):
            return JsonResponse({"error": "live_data_disabled"}, status=403)

        isin = request.GET.get("isin", "").strip().upper()
        if not _ISIN_RE.match(isin):
            return JsonResponse({"error": "invalid_isin"}, status=400)

        try:
            autofill = fetch_holding_autofill(isin)
        except MarketDataError as exc:
            return JsonResponse({"error": str(exc)}, status=502)

        return JsonResponse(
            {
                "code": autofill.code,
                "name": autofill.name,
                "issuer": autofill.issuer,
                "fees": float(autofill.fees) if autofill.fees is not None else None,
                "initial_value": float(autofill.initial_value)
                if autofill.initial_value is not None
                else None,
                "currency": autofill.currency,
            }
        )


@method_decorator(login_required, name="dispatch")
class InvestmentLiveChangeApiView(View):
    """Return today's live intraday change per investment account, for dashboard badges."""

    def get(self, request):
        if not getattr(request.user.profile, "live_data_enabled", True):
            return JsonResponse({"enabled": False})

        accounts_data = {}
        alerts = []
        for account in InvestmentAccount.objects.filter(is_active=True):
            current_total = Decimal("0")
            previous_total = Decimal("0")
            as_of = None
            holdings = InvestmentAccountHolding.objects.filter(
                account=account, is_active=True
            )
            for holding in holdings:
                if not holding.isin:
                    continue
                try:
                    quote = get_live_quote(holding.isin)
                except MarketDataError:
                    continue
                if quote.currency != account.currency or quote.previous_close is None:
                    continue
                quantity = holding.get_quantity() or Decimal("0")
                current_total += quote.price * quantity
                previous_total += quote.previous_close * quantity
                as_of = quote.as_of

            # Skip accounts with no usable quoted holdings (nothing to compare against).
            if previous_total <= 0:
                continue

            change_percent = float(
                (current_total - previous_total) / previous_total * 100
            )
            accounts_data[str(account.pk)] = {
                "live_change_percent": round(change_percent, 2),
                "as_of": as_of.isoformat() if as_of else None,
            }
            if change_percent < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Live: down {abs(change_percent):.2f}% today",
                        "type_css": "danger",
                    }
                )

        return JsonResponse(
            {"enabled": True, "accounts": accounts_data, "alerts": alerts}
        )
