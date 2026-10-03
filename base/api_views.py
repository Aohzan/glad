"""API views for the base app — lightweight JSON endpoints used by the dashboard."""

import datetime
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from moneyed import Money

from base.services.dashboard import default_currency
from base.services.operations import recent_operations
from base.services.snapshots import month_starts, net_worth_history
from finance.models.investment_account import (
    InvestmentAccount,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from glad.settings import DEFAULT_CURRENCY
from property.models import Property
from property.models.scpi import SCPIInvestment


def _resolve_default_currency(
    total_investment_accounts_by_currency: dict,
    total_saving_accounts_by_currency: dict,
    total_properties_value_by_currency: dict,
) -> str:
    if total_investment_accounts_by_currency:
        return next(iter(total_investment_accounts_by_currency.keys()))
    if total_saving_accounts_by_currency:
        return next(iter(total_saving_accounts_by_currency.keys()))
    if total_properties_value_by_currency:
        return next(iter(total_properties_value_by_currency.keys()))
    return DEFAULT_CURRENCY


def _sum_by_currency(items, value_fn) -> dict[str, Money]:
    """Group *items* by currency and sum their values using *value_fn*.

    Returns a ``{currency_str: Money}`` dict.
    """
    by_curr: dict[str, list] = defaultdict(list)
    for item in items:
        by_curr[item.currency].append(item)
    return {
        currency: sum((value_fn(i) for i in group), Money(0, currency))
        for currency, group in by_curr.items()
    }


def _get_currency_totals() -> dict:
    """Compute per-currency account/property totals. Shared by multiple API views."""
    saving_accounts = SavingAccount.objects.filter(is_active=True)
    saving_by_currency = _sum_by_currency(saving_accounts, lambda a: a.get_value())

    investment_accounts = InvestmentAccount.objects.filter(is_active=True)
    investment_by_currency = _sum_by_currency(
        investment_accounts, lambda a: a.current_value
    )

    properties = Property.objects.filter(is_active=True)
    properties_net_by_currency = _sum_by_currency(properties, lambda p: p.net_value)
    properties_gross_by_currency = _sum_by_currency(properties, lambda p: p.gross_value)

    # SCPI investments — use estimated value (accounts for dismemberment)
    today = datetime.date.today()
    scpi_investments = SCPIInvestment.objects.select_related("scpi").all()
    scpi_by_currency = _sum_by_currency(
        scpi_investments, lambda inv: inv.get_estimated_value(today)
    )

    other_assets = OtherAsset.objects.filter(is_active=True)
    other_by_currency = _sum_by_currency(other_assets, lambda a: a.current_value)

    all_currencies = set(
        list(investment_by_currency)
        + list(saving_by_currency)
        + list(properties_net_by_currency)
        + list(scpi_by_currency)
        + list(other_by_currency)
    )
    net_worth_by_currency: dict[str, Money] = {}
    for currency in all_currencies:
        net_worth_by_currency[currency] = (
            saving_by_currency.get(currency, Money(0, currency))
            + investment_by_currency.get(currency, Money(0, currency))
            + properties_net_by_currency.get(currency, Money(0, currency))
            + scpi_by_currency.get(currency, Money(0, currency))
            + other_by_currency.get(currency, Money(0, currency))
        )

    default_currency = _resolve_default_currency(
        investment_by_currency, saving_by_currency, properties_net_by_currency
    )

    return {
        "saving_accounts": saving_accounts,
        "investment_accounts": investment_accounts,
        "properties": properties,
        "scpi_investments": scpi_investments,
        "saving_by_currency": saving_by_currency,
        "investment_by_currency": investment_by_currency,
        "properties_net_by_currency": properties_net_by_currency,
        "properties_gross_by_currency": properties_gross_by_currency,
        "scpi_by_currency": scpi_by_currency,
        "other_assets": other_assets,
        "other_by_currency": other_by_currency,
        "net_worth_by_currency": net_worth_by_currency,
        "default_currency": default_currency,
    }


@method_decorator(login_required, name="dispatch")
class NetWorthApiView(View):
    """Return hero-banner totals and 30-day progression for the dashboard."""

    def get(self, request):
        totals = _get_currency_totals()
        dc = totals["default_currency"]
        saving_by_currency = totals["saving_by_currency"]
        investment_by_currency = totals["investment_by_currency"]
        properties_net_by_currency = totals["properties_net_by_currency"]
        net_worth_by_currency = totals["net_worth_by_currency"]
        scpi_by_currency = totals["scpi_by_currency"]

        total_savings = saving_by_currency.get(dc, Money(0, dc))
        total_investments = investment_by_currency.get(dc, Money(0, dc))
        total_properties_net = properties_net_by_currency.get(dc, Money(0, dc))
        total_scpi = scpi_by_currency.get(dc, Money(0, dc))
        total_other = totals["other_by_currency"].get(dc, Money(0, dc))
        total_net_worth = (
            total_savings
            + total_investments
            + total_properties_net
            + total_scpi
            + total_other
        )

        # 30-day progression
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        global_progression = 0.0
        try:
            saving_accounts = totals["saving_accounts"]
            investment_accounts = totals["investment_accounts"]
            properties = totals["properties"]

            historical_saving = list(saving_accounts)
            historical_saving.extend(
                SavingAccount.objects.filter(
                    is_active=False, closing_date__gt=thirty_days_ago.date()
                )
            )
            old_saving = Money(0, dc)
            for account in historical_saving:
                if account.currency == dc:
                    try:
                        old_saving += account.get_value(max_date=thirty_days_ago)
                    except TypeError:
                        old_saving += account.get_value(max_date=thirty_days_ago.date())
                    except Exception:
                        old_saving += account.get_value()

            historical_investment = list(investment_accounts)
            historical_investment.extend(
                InvestmentAccount.objects.filter(
                    is_active=False, closing_date__gt=thirty_days_ago.date()
                )
            )
            old_investment = Money(0, dc)
            for account in historical_investment:
                if account.currency == dc:
                    try:
                        old_investment += account.get_value(max_date=thirty_days_ago)
                    except TypeError:
                        old_investment += account.get_value(
                            max_date=thirty_days_ago.date()
                        )
                    except Exception:
                        old_investment += account.get_value()

            old_property = Money(0, dc)
            for prop in properties:
                if prop.currency == dc and prop.buying_date <= thirty_days_ago.date():
                    try:
                        old_property += prop.net_value
                    except Exception:
                        pass

            old_other = sum(
                (
                    asset.get_value(thirty_days_ago.date()).amount
                    for asset in OtherAsset.objects.all()
                    if asset.currency == dc
                ),
                Decimal(0),
            )
            old_total = (
                old_saving.amount
                + old_investment.amount
                + old_property.amount
                + old_other
            )
            current_total = (
                total_savings.amount
                + total_investments.amount
                + total_properties_net.amount
                + total_scpi.amount
                + total_other.amount
            )
            if old_total > 0:
                global_progression = round(
                    float((current_total - old_total) / old_total * 100), 2
                )
        except Exception:
            global_progression = 0.0

        return JsonResponse(
            {
                "total_net_worth": float(total_net_worth.amount),
                "total_investments": float(total_investments.amount),
                "total_savings": float(total_savings.amount),
                "total_properties_net": float(total_properties_net.amount),
                "total_scpi": float(total_scpi.amount),
                "total_other": float(total_other.amount),
                "has_investments": totals["investment_accounts"].exists(),
                "has_savings": totals["saving_accounts"].exists(),
                "has_properties": totals["properties"].exists(),
                "has_scpi": totals["scpi_investments"].exists(),
                "has_other": totals["other_assets"].exists(),
                "global_progression": global_progression,
                "currency": dc,
                "net_worth_by_currency": {
                    cur: float(val.amount) for cur, val in net_worth_by_currency.items()
                },
            }
        )


@method_decorator(login_required, name="dispatch")
class PatrimonyChartApiView(View):
    """Return patrimony evolution series for the evolution chart."""

    #: Accepted ``range`` values, in years.
    RANGES = (1, 2, 5, 10)
    DEFAULT_RANGE = 2

    def get(self, request):
        dc = default_currency()
        try:
            years = int(request.GET.get("range", self.DEFAULT_RANGE))
        except ValueError:
            years = self.DEFAULT_RANGE
        if years not in self.RANGES:
            years = self.DEFAULT_RANGE
        # The last point is today, so that it matches the hero card figures.
        today = datetime.date.today()
        months = [*month_starts(years * 12, today)[:-1], today]
        history = net_worth_history(months, dc, today)

        def series(name: str) -> list[float]:
            return [float(values[name]) for values in history]

        net = [
            float(
                v["savings"]
                + v["investments"]
                + v["properties_net"]
                + v["scpi"]
                + v["other"]
            )
            for v in history
        ]
        # loans = gross - net (the part of the properties still owed)
        loans = [float(v["properties_gross"] - v["properties_net"]) for v in history]
        return JsonResponse(
            {
                "currency": dc,
                "dates": [m.isoformat() for m in months],
                "months": [m.strftime("%b %Y") for m in months],
                "net": net,
                "gross": [n + debt for n, debt in zip(net, loans, strict=True)],
                "debt": loans,
                "investments": series("investments"),
                "savings": series("savings"),
                "properties_net": series("properties_net"),
                "properties_loans": loans,
                "scpi": series("scpi"),
                "other": series("other"),
            }
        )


@method_decorator(login_required, name="dispatch")
class RecentOperationsApiView(View):
    """Return the 5 most recent operations."""

    #: Bootstrap contextual class of each kind of operation.
    TYPE_CSS = {
        "saving_value": "success",
        "investment_cash": "primary",
        "holding_value": "info",
    }

    def get(self, request):
        return JsonResponse(
            {
                "operations": [
                    {
                        "label": f"{op.label}: {op.target}",
                        "amount": float(op.amount.amount),
                        "currency": str(op.amount.currency),
                        "date": op.date.isoformat(),
                        "icon": op.icon,
                        "type_css": self.TYPE_CSS.get(op.kind, "secondary"),
                    }
                    for op in recent_operations(5)
                ]
            }
        )


@method_decorator(login_required, name="dispatch")
class AlertsApiView(View):
    """Return accounts with a >5% negative 30-day progression."""

    def get(self, request):
        days = 30
        alerts = []

        for account in SavingAccount.objects.filter(is_active=True):
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )

        for account in InvestmentAccount.objects.filter(is_active=True):
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )

        return JsonResponse({"alerts": alerts})
