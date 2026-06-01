"""CRUD views for SCPI investments, share prices, and dividends."""

import datetime
import json
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from property.forms import (
    SCPIDividendForm,
    SCPIForm,
    SCPIInvestmentForm,
    SCPISharePriceForm,
)
from property.models import SCPI, SCPIDividend, SCPIInvestment, SCPISharePrice

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _iter_months(start: datetime.date, end: datetime.date):
    """Yield (year, month) pairs from start to end inclusive."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _compute_fund_data(fund: SCPI, today: datetime.date) -> dict:
    """Compute aggregate stats and chart data for a single SCPI fund."""
    investments = list(fund.investments.all())
    dividends = list(fund.dividends.order_by("-payment_date"))

    total_invested: Money | None = None
    total_resale: Money | None = None
    min_subscription_date: datetime.date | None = None
    currency = "EUR"

    for inv in investments:
        invested = inv.get_total_invested()
        resale = inv.get_estimated_resale_value(today)
        if hasattr(invested, "currency"):
            currency = str(invested.currency)

        if total_invested is None:
            total_invested = invested
            total_resale = resale
        else:
            total_invested = Money(
                total_invested.amount + invested.amount, str(total_invested.currency)
            )
            assert total_resale is not None  # noqa: S101 — set together with total_invested
            total_resale = Money(
                total_resale.amount + resale.amount,
                str(total_resale.currency),
            )

        if (
            min_subscription_date is None
            or inv.subscription_date < min_subscription_date
        ):
            min_subscription_date = inv.subscription_date

    # Total dividends (fund-level)
    total_dividends = fund.get_total_dividends_received()
    last_12mo_start = today - datetime.timedelta(days=365)
    last_year_dividends = fund.get_dividends_received_in_period(last_12mo_start, today)

    # Capital gain
    capital_gain: Money | None = None
    gain_pct: Decimal | None = None
    if total_resale is not None and total_invested is not None:
        capital_gain = Money(
            total_resale.amount - total_invested.amount,
            str(total_resale.currency),
        )
        if total_invested.amount > 0:
            gain_pct = (
                capital_gain.amount / total_invested.amount * Decimal("100")
            ).quantize(Decimal("0.01"))

    # Net rentability (last 12 months dividends / total invested)
    net_rentability: Decimal = Decimal("0")
    if total_invested is not None and total_invested.amount > 0:
        net_rentability = (
            last_year_dividends.amount / total_invested.amount * Decimal("100")
        ).quantize(Decimal("0.01"))

    # Total net rentability (all-time dividends / total invested)
    total_net_rentability: Decimal = Decimal("0")
    if total_invested is not None and total_invested.amount > 0:
        total_net_rentability = (
            total_dividends.amount / total_invested.amount * Decimal("100")
        ).quantize(Decimal("0.01"))

    # Growth rentability (annualized capital gain since first investment)
    growth_rentability: Decimal = Decimal("0")
    if gain_pct is not None and min_subscription_date is not None:
        years = Decimal(str((today - min_subscription_date).days)) / Decimal("365.25")
        if years > 0:
            growth_rentability = (gain_pct / years).quantize(Decimal("0.01"))

    # Last 12 months growth (share price change over past year)
    last_12mo_growth_pct: Decimal = Decimal("0")
    if total_invested is not None and total_invested.amount > 0:
        resale_12mo_ago: Money | None = None
        date_12mo_ago = today - datetime.timedelta(days=365)
        for inv in investments:
            r = inv.get_estimated_resale_value(date_12mo_ago)
            if resale_12mo_ago is None:
                resale_12mo_ago = r
            else:
                resale_12mo_ago = Money(
                    resale_12mo_ago.amount + r.amount, str(resale_12mo_ago.currency)
                )
        if resale_12mo_ago is not None and total_resale is not None:
            last_12mo_gain = total_resale.amount - resale_12mo_ago.amount
            last_12mo_growth_pct = (
                last_12mo_gain / total_invested.amount * Decimal("100")
            ).quantize(Decimal("0.01"))

    # ── Monthly chart data ────────────────────────────────────────────────────
    # Line: cumulative invested per month since first acquisition
    # Bar: total dividends per month (on second y-axis)
    chart_months: list[str] = []
    chart_invested_monthly: list[float] = []
    chart_dividend_monthly: list[float] = []

    if min_subscription_date is not None:
        sorted_investments = sorted(investments, key=lambda i: i.subscription_date)
        div_by_month: dict[tuple[int, int], Decimal] = {}
        for div in dividends:
            key = (div.payment_date.year, div.payment_date.month)
            div_by_month[key] = (
                div_by_month.get(key, Decimal("0")) + div.net_amount.amount
            )

        cumulative = Decimal("0")
        inv_idx = 0
        for year, month in _iter_months(min_subscription_date, today):
            while inv_idx < len(sorted_investments):
                sub = sorted_investments[inv_idx].subscription_date
                if sub.year < year or (sub.year == year and sub.month <= month):
                    cumulative += (
                        sorted_investments[inv_idx].get_total_invested().amount
                    )
                    inv_idx += 1
                else:
                    break
            month_label = f"{year}-{month:02d}"
            chart_months.append(month_label)
            chart_invested_monthly.append(float(cumulative))
            chart_dividend_monthly.append(
                float(div_by_month.get((year, month), Decimal("0")))
            )

    # ── Dividend table JSON ────────────────────────────────────────────────────
    dividends_json = [
        {
            "id": div.pk,
            "payment_date": div.payment_date.strftime("%Y-%m-%d"),
            "gross_amount": str(div.gross_amount.amount) if div.gross_amount else None,
            "net_amount": str(div.net_amount.amount),
            "notes": div.notes or "",
        }
        for div in dividends
    ]

    return {
        "fund": fund,
        "investments": investments,
        "total_invested": total_invested,
        "total_resale": total_resale,
        "total_dividends": total_dividends,
        "last_year_dividends": last_year_dividends,
        "capital_gain": capital_gain,
        "gain_pct": gain_pct,
        "net_rentability": net_rentability,
        "total_net_rentability": total_net_rentability,
        "growth_rentability": growth_rentability,
        "last_12mo_growth_pct": last_12mo_growth_pct,
        "currency": currency,
        "chart_months": json.dumps(chart_months),
        "chart_invested_monthly": json.dumps(chart_invested_monthly),
        "chart_dividend_monthly": json.dumps(chart_dividend_monthly),
        "dividends_json": dividends_json,
    }


# ─── SCPI List ────────────────────────────────────────────────────────────────


def scpi_list(request: HttpRequest) -> HttpResponse:
    """List all SCPI funds with fund-level aggregate statistics."""
    today = datetime.date.today()
    scpi_funds = SCPI.objects.prefetch_related(
        "share_prices", "investments", "dividends"
    ).order_by("name")

    fund_data = []
    global_total_invested: Money | None = None
    global_total_resale: Money | None = None
    global_total_dividends: Money | None = None

    for fund in scpi_funds:
        data = _compute_fund_data(fund, today)
        fund_data.append(data)

        if data["total_invested"] is not None:
            if global_total_invested is None:
                global_total_invested = data["total_invested"]
                global_total_resale = data["total_resale"]
                global_total_dividends = data["total_dividends"]
            else:
                global_total_invested = Money(
                    global_total_invested.amount + data["total_invested"].amount,
                    str(global_total_invested.currency),
                )
                if global_total_resale is not None and data["total_resale"] is not None:
                    global_total_resale = Money(
                        global_total_resale.amount + data["total_resale"].amount,
                        str(global_total_resale.currency),
                    )
                if (
                    global_total_dividends is not None
                    and data["total_dividends"] is not None
                ):
                    global_total_dividends = Money(
                        global_total_dividends.amount + data["total_dividends"].amount,
                        str(global_total_dividends.currency),
                    )

    global_gain_pct: Decimal | None = None
    if (
        global_total_resale is not None
        and global_total_invested is not None
        and global_total_invested.amount > 0
    ):
        global_capital_gain = global_total_resale.amount - global_total_invested.amount
        global_gain_pct = (
            global_capital_gain / global_total_invested.amount * Decimal("100")
        ).quantize(Decimal("0.01"))

    global_net_rentability: Decimal = Decimal("0")
    funds_with_net_rentability = [d for d in fund_data if d["net_rentability"] > 0]
    if funds_with_net_rentability:
        global_net_rentability = (
            sum(d["net_rentability"] for d in funds_with_net_rentability)
            / len(funds_with_net_rentability)
        ).quantize(Decimal("0.01"))

    return render(
        request,
        "property/scpi_list.html",
        {
            "fund_data": fund_data,
            "global_total_invested": global_total_invested,
            "global_total_resale": global_total_resale,
            "global_total_dividends": global_total_dividends,
            "global_gain_pct": global_gain_pct,
            "global_net_rentability": global_net_rentability,
        },
    )


# ─── SCPI fund detail ─────────────────────────────────────────────────────────


def scpi_fund_detail(request: HttpRequest, scpi_pk: int) -> HttpResponse:
    """Detail view for a SCPI fund — all investments and profitability."""
    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)
    today = datetime.date.today()
    data = _compute_fund_data(scpi_obj, today)

    investment_rows = []
    for inv in data["investments"]:
        investment_rows.append(
            {
                "obj": inv,
                "total_invested": inv.get_total_invested(),
                "estimated_resale": inv.get_estimated_resale_value(today),
                "capital_gain": inv.get_capital_gain(today),
            }
        )

    return render(
        request,
        "property/scpi_fund_detail.html",
        {
            **data,
            "scpi": scpi_obj,
            "today": today,
            "investment_rows": investment_rows,
        },
    )


# ─── SCPI fund CRUD ───────────────────────────────────────────────────────────


def edit_scpi(request: HttpRequest, scpi_pk: int | None = None) -> HttpResponse:
    """Create or edit a SCPI fund."""
    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk) if scpi_pk else None

    if request.method == "POST":
        form = SCPIForm(request.POST, instance=scpi_obj)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                _("SCPI updated successfully.")
                if scpi_obj
                else _("SCPI created successfully."),
            )
            return redirect("property:scpi_list")
    else:
        form = SCPIForm(instance=scpi_obj)

    return render(
        request,
        "property/scpi_fund_form.html",
        {"form": form, "scpi": scpi_obj},
    )


def delete_scpi(request: HttpRequest, scpi_pk: int) -> HttpResponse:
    """Delete a SCPI fund. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:scpi_list")

    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)
    scpi_obj.delete()
    messages.success(request, _("SCPI deleted successfully."))
    return redirect("property:scpi_list")


# ─── SCPI share price CRUD ────────────────────────────────────────────────────


def add_scpi_share_price(request: HttpRequest, scpi_pk: int) -> HttpResponse:
    """Add a share price record for a SCPI fund."""
    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)

    if request.method == "POST":
        form = SCPISharePriceForm(request.POST)
        if form.is_valid():
            share_price = form.save(commit=False)
            share_price.scpi = scpi_obj
            share_price.save()
            messages.success(request, _("Share price added successfully."))
            return redirect("property:scpi_fund_detail", scpi_pk=scpi_obj.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = SCPISharePriceForm()

    return render(
        request,
        "property/scpi_share_price_form.html",
        {"form": form, "scpi": scpi_obj},
    )


def delete_scpi_share_price(
    request: HttpRequest, scpi_pk: int, price_pk: int
) -> HttpResponse:
    """Delete a share price record. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:scpi_list")

    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)
    price = get_object_or_404(SCPISharePrice, pk=price_pk, scpi=scpi_obj)
    price.delete()
    messages.success(request, _("Share price deleted successfully."))
    return redirect("property:scpi_fund_detail", scpi_pk=scpi_obj.pk)


# ─── SCPI Investment CRUD ─────────────────────────────────────────────────────


def edit_scpi_investment(
    request: HttpRequest, investment_pk: int | None = None
) -> HttpResponse:
    """Create or edit a SCPI investment."""
    investment = (
        get_object_or_404(SCPIInvestment, pk=investment_pk) if investment_pk else None
    )

    if request.method == "POST":
        form = SCPIInvestmentForm(request.POST, instance=investment)
        if form.is_valid():
            saved = form.save()
            messages.success(
                request,
                _("Investment updated successfully.")
                if investment
                else _("Investment created successfully."),
            )
            return redirect("property:scpi_fund_detail", scpi_pk=saved.scpi.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = SCPIInvestmentForm(instance=investment)

    return render(
        request,
        "property/scpi_investment_form.html",
        {"form": form, "investment": investment},
    )


def delete_scpi_investment(request: HttpRequest, investment_pk: int) -> HttpResponse:
    """Delete a SCPI investment. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:scpi_list")

    investment = get_object_or_404(SCPIInvestment, pk=investment_pk)
    scpi_pk = investment.scpi.pk
    investment.delete()
    messages.success(request, _("Investment deleted successfully."))
    return redirect("property:scpi_fund_detail", scpi_pk=scpi_pk)


# ─── Dividend CRUD ────────────────────────────────────────────────────────────


def edit_scpi_dividend(
    request: HttpRequest,
    scpi_pk: int,
    dividend_pk: int | None = None,
) -> HttpResponse:
    """Create or edit a dividend for a SCPI fund."""
    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)
    dividend = (
        get_object_or_404(SCPIDividend, pk=dividend_pk, scpi=scpi_obj)
        if dividend_pk
        else None
    )

    if request.method == "POST":
        form = SCPIDividendForm(request.POST, instance=dividend)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.scpi = scpi_obj
            saved.save()
            messages.success(
                request,
                _("Dividend updated successfully.")
                if dividend
                else _("Dividend recorded successfully."),
            )
            return redirect("property:scpi_fund_detail", scpi_pk=scpi_obj.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = SCPIDividendForm(instance=dividend)

    return render(
        request,
        "property/scpi_dividend_form.html",
        {"form": form, "scpi": scpi_obj, "dividend": dividend},
    )


def delete_scpi_dividend(
    request: HttpRequest, scpi_pk: int, dividend_pk: int
) -> HttpResponse:
    """Delete a dividend record. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:scpi_list")

    scpi_obj = get_object_or_404(SCPI, pk=scpi_pk)
    dividend = get_object_or_404(SCPIDividend, pk=dividend_pk, scpi=scpi_obj)
    dividend.delete()
    messages.success(request, _("Dividend deleted successfully."))
    return redirect("property:scpi_fund_detail", scpi_pk=scpi_obj.pk)
