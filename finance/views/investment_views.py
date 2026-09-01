"""Views for investment account CRUD operations."""

import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from moneyed import Money

from finance.forms import (
    BackfillHoldingHistoryForm,
    InvestmentAccountCashForm,
    InvestmentAccountDepositForm,
    InvestmentAccountForm,
    InvestmentAccountHoldingForm,
    InvestmentAccountHoldingHistoryForm,
)
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.services.market_data import MarketDataError, fetch_historical_prices
from finance.views.crud_views import _delete_account_related, _edit_account_related

DETAIL_URL = "finance:investment_detail"


# ─── Investment account CRUD ─────────────────────────────────────────────────


def investment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Detail view for an investment account."""
    account = get_object_or_404(InvestmentAccount, pk=pk)
    holdings = InvestmentAccountHolding.objects.filter(account=account).order_by("name")
    cash_values = account.cash_values.order_by("-value_date")  # type: ignore[union-attr]
    deposits = account.deposits.order_by("-deposit_date")
    progression = account.get_progression(days=30)
    total_deposits, capital_gain = account.compute_capital_gain()

    return render(
        request,
        "finance/investment_detail.html",
        {
            "account": account,
            "holdings": holdings,
            "cash_values": cash_values,
            "deposits": deposits,
            "progression": progression,
            "total_deposits": total_deposits,
            "capital_gain": capital_gain,
        },
    )


def create_investment(request: HttpRequest) -> HttpResponse:
    """Create a new investment account."""
    if request.method == "POST":
        form = InvestmentAccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Investment account created successfully."))
            return redirect(DETAIL_URL, pk=form.instance.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = InvestmentAccountForm()

    return render(
        request,
        "finance/edit_investment.html",
        {
            "form": form,
            "account_back_url": reverse("finance:index"),
            "account_back_label": "Finance",
            "account_cancel_url": reverse("finance:index"),
        },
    )


def edit_investment(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing investment account."""
    account = get_object_or_404(InvestmentAccount, pk=pk)

    if request.method == "POST":
        form = InvestmentAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, _("Investment account updated successfully."))
            return redirect(DETAIL_URL, pk=account.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = InvestmentAccountForm(instance=account)

    return render(
        request,
        "finance/edit_investment.html",
        {
            "form": form,
            "account": account,
            "account_back_url": reverse("finance:investment_detail", args=[account.pk]),
            "account_back_label": str(account),
            "account_cancel_url": reverse(
                "finance:investment_detail", args=[account.pk]
            ),
        },
    )


def delete_investment(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an investment account."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect(DETAIL_URL, pk=pk)

    account = get_object_or_404(InvestmentAccount, pk=pk)
    account.delete()
    messages.success(request, _("Investment account deleted successfully."))
    return redirect("finance:index")


# ─── Holding CRUD ─────────────────────────────────────────────────────────────


def edit_investment_holding(
    request: HttpRequest, account_pk: int, holding_pk: int | None = None
) -> HttpResponse:
    """Create or edit an investment account holding."""
    return _edit_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountHolding,
        object_pk=holding_pk,
        form_class=InvestmentAccountHoldingForm,
        template="finance/edit_investment_holding.html",
        context_key="holding",
        success_message=_("Holding saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#holdings-panel",
    )


def delete_investment_holding(
    request: HttpRequest, account_pk: int, holding_pk: int
) -> HttpResponse:
    """Delete an investment account holding."""
    return _delete_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountHolding,
        object_pk=holding_pk,
        success_message=_("Holding deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#holdings-panel",
    )


def holding_detail(
    request: HttpRequest, account_pk: int, holding_pk: int
) -> HttpResponse:
    """Detail view for an investment account holding."""
    account = get_object_or_404(InvestmentAccount, pk=account_pk)
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account=account
    )
    history = holding.investmentaccountholdinghistory_set.all()  # ty: ignore[unresolved-attribute]

    return render(
        request,
        "finance/holding_detail.html",
        {
            "account": account,
            "holding": holding,
            "history": history,
        },
    )


# ─── Investment deposit CRUD ─────────────────────────────────────────────────


def edit_investment_deposit(
    request: HttpRequest, account_pk: int, deposit_pk: int | None = None
) -> HttpResponse:
    """Create or edit an investment account deposit."""
    return _edit_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountDeposit,
        object_pk=deposit_pk,
        form_class=InvestmentAccountDepositForm,
        template="finance/edit_investment_deposit.html",
        context_key="deposit",
        success_message=_("Deposit saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#deposits-panel",
    )


def delete_investment_deposit(
    request: HttpRequest, account_pk: int, deposit_pk: int
) -> HttpResponse:
    """Delete an investment account deposit."""
    return _delete_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountDeposit,
        object_pk=deposit_pk,
        success_message=_("Deposit deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#deposits-panel",
    )


# ─── Investment cash CRUD ────────────────────────────────────────────────────


def edit_investment_cash(
    request: HttpRequest, account_pk: int, cash_pk: int | None = None
) -> HttpResponse:
    """Create or edit an investment account cash entry."""
    return _edit_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountCash,
        object_pk=cash_pk,
        form_class=InvestmentAccountCashForm,
        template="finance/edit_investment_cash.html",
        context_key="cash_entry",
        success_message=_("Cash entry saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#cash-panel",
    )


def delete_investment_cash(
    request: HttpRequest, account_pk: int, cash_pk: int
) -> HttpResponse:
    """Delete an investment account cash entry."""
    return _delete_account_related(
        request,
        account_pk=account_pk,
        account_model=InvestmentAccount,
        model=InvestmentAccountCash,
        object_pk=cash_pk,
        success_message=_("Cash entry deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#cash-panel",
    )


# ─── Holding history CRUD ────────────────────────────────────────────────────


def edit_holding_history(
    request: HttpRequest,
    account_pk: int,
    holding_pk: int,
    history_pk: int | None = None,
) -> HttpResponse:
    """Create or edit an investment holding history entry."""
    account = get_object_or_404(InvestmentAccount, pk=account_pk)
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account=account
    )
    obj = (
        get_object_or_404(
            InvestmentAccountHoldingHistory, pk=history_pk, holding=holding
        )
        if history_pk
        else None
    )
    holding_detail_url = reverse(
        "finance:holding_detail",
        kwargs={"account_pk": account_pk, "holding_pk": holding_pk},
    )

    if request.method == "POST":
        form = InvestmentAccountHoldingHistoryForm(request.POST, instance=obj)
        if form.is_valid():
            created = form.save(commit=False)
            created.holding = holding
            created.save()
            messages.success(request, _("Holding history entry saved successfully."))
            return HttpResponseRedirect(holding_detail_url)
        messages.error(request, _("Please correct the errors below."))
    else:
        initial = {}
        if obj is None:
            prefill_value = request.GET.get("prefill_value")
            prefill_quantity = request.GET.get("prefill_quantity")
            if prefill_value:
                try:
                    initial["value"] = Money(
                        Decimal(prefill_value), holding.account.currency
                    )
                except InvalidOperation:
                    pass
            if prefill_quantity:
                initial["quantity"] = prefill_quantity
        form = InvestmentAccountHoldingHistoryForm(instance=obj, initial=initial)

    return render(
        request,
        "finance/edit_holding_history.html",
        {
            "account": account,
            "holding": holding,
            "history": obj,
            "form": form,
        },
    )


def delete_holding_history(
    request: HttpRequest,
    account_pk: int,
    holding_pk: int,
    history_pk: int,
) -> HttpResponse:
    """Delete an investment holding history entry."""
    holding_detail_url = reverse(
        "finance:holding_detail",
        kwargs={"account_pk": account_pk, "holding_pk": holding_pk},
    )
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return HttpResponseRedirect(holding_detail_url)

    account = get_object_or_404(InvestmentAccount, pk=account_pk)
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account=account
    )
    obj = get_object_or_404(
        InvestmentAccountHoldingHistory, pk=history_pk, holding=holding
    )
    obj.delete()
    messages.success(request, _("Holding history entry deleted successfully."))
    return HttpResponseRedirect(holding_detail_url)


def backfill_holding_history(
    request: HttpRequest, account_pk: int, holding_pk: int
) -> HttpResponse:
    """Fill missing monthly history entries for a holding from live market data."""
    account = get_object_or_404(InvestmentAccount, pk=account_pk)
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account=account
    )
    holding_detail_url = reverse(
        "finance:holding_detail",
        kwargs={"account_pk": account_pk, "holding_pk": holding_pk},
    )

    if not holding.isin or not getattr(
        request.user.profile,  # ty: ignore[unresolved-attribute]
        "live_data_enabled",
        True,
    ):
        messages.error(
            request, _("Live market data is not available for this holding.")
        )
        return HttpResponseRedirect(holding_detail_url)

    if request.method == "POST":
        form = BackfillHoldingHistoryForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            try:
                points, currency = fetch_historical_prices(
                    holding.isin, start_date, end_date
                )
            except MarketDataError as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(holding_detail_url)

            if currency != account.currency:
                messages.warning(
                    request,
                    _(
                        "Quote currency ({quote}) differs from the account"
                        " currency ({account}); no entries were created."
                    ).format(quote=currency, account=account.currency),
                )
                return HttpResponseRedirect(holding_detail_url)

            created_count = 0
            skipped_existing = 0
            for point in points:
                month_exists = InvestmentAccountHoldingHistory.objects.filter(
                    holding=holding,
                    valuation_date__year=point.date.year,
                    valuation_date__month=point.date.month,
                ).exists()
                if month_exists:
                    skipped_existing += 1
                    continue

                quantity = holding.get_quantity(max_date=point.date)
                if not quantity:
                    continue

                try:
                    with transaction.atomic():
                        InvestmentAccountHoldingHistory.objects.create(
                            holding=holding,
                            value=Money(point.price * quantity, account.currency),
                            quantity=quantity,
                            valuation_date=datetime.datetime.combine(
                                point.date, datetime.time.min
                            ),
                        )
                    created_count += 1
                except IntegrityError:
                    skipped_existing += 1

            if created_count:
                messages.success(
                    request,
                    _("{count} history entries created.").format(count=created_count),
                )
            else:
                messages.info(request, _("No new history entries were created."))
            return HttpResponseRedirect(holding_detail_url)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = BackfillHoldingHistoryForm(
            initial={
                "start_date": holding.initial_valuation_date,
                "end_date": datetime.date.today(),
            }
        )

    return render(
        request,
        "finance/backfill_holding_history.html",
        {"account": account, "holding": holding, "form": form},
    )


@require_POST  # type: ignore
def toggle_investment_favorite(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle the is_favorite flag for an investment account."""
    account = get_object_or_404(InvestmentAccount, pk=pk)
    account.is_favorite = not account.is_favorite
    account.save(update_fields=["is_favorite"])
    return redirect(request.META.get("HTTP_REFERER") or reverse("finance:index"))
