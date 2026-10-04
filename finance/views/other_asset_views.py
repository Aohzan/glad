"""Views for the other assets (vehicles, precious metals, crypto…)."""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from moneyed import Money

from finance.forms import OtherAssetForm, OtherAssetValueForm
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.services.market_data import MarketDataError, get_live_quote
from finance.views.crud_views import _delete_account_related, _edit_account_related

DETAIL_URL = "finance:other_asset_detail"
LIST_URL = "finance:other_asset_list"


def other_asset_list(request: HttpRequest) -> HttpResponse:
    """List the other assets with their total value per currency."""
    assets = list(OtherAsset.objects.all())
    totals: dict[str, Money] = {}
    rows = []
    for asset in assets:
        value = asset.current_value
        if asset.is_active:
            currency = str(value.currency)
            totals[currency] = totals.get(currency, Money(0, currency)) + value
        rows.append({"asset": asset, "value": value})
    return render(
        request,
        "finance/other_asset_list.html",
        {"rows": rows, "totals": totals},
    )


def other_asset_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Detail page of an other asset with its value history."""
    asset = get_object_or_404(OtherAsset, pk=pk)
    return render(
        request,
        "finance/other_asset_detail.html",
        {
            "asset": asset,
            "values": asset.values.order_by("-value_date"),
            "live_data_enabled": _live_data_enabled(request),
        },
    )


def _save_asset_form(request: HttpRequest, asset: OtherAsset | None) -> HttpResponse:
    if request.method == "POST":
        form = OtherAssetForm(request.POST, instance=asset)
        if form.is_valid():
            saved = form.save()
            messages.success(request, _("Asset saved."))
            return redirect(DETAIL_URL, pk=saved.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = OtherAssetForm(instance=asset)
    return render(
        request, "finance/edit_other_asset.html", {"form": form, "asset": asset}
    )


def create_other_asset(request: HttpRequest) -> HttpResponse:
    """Create an other asset."""
    return _save_asset_form(request, None)


def edit_other_asset(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an other asset."""
    return _save_asset_form(request, get_object_or_404(OtherAsset, pk=pk))


@require_POST  # type: ignore
def delete_other_asset(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an other asset and its value history."""
    get_object_or_404(OtherAsset, pk=pk).delete()
    messages.success(request, _("Asset deleted."))
    return redirect(LIST_URL)


def edit_other_asset_value(
    request: HttpRequest, asset_pk: int, value_pk: int | None = None
) -> HttpResponse:
    """Create or edit a value entry of an other asset."""
    return _edit_account_related(
        request,
        account_pk=asset_pk,
        account_model=OtherAsset,
        model=OtherAssetValue,
        object_pk=value_pk,
        form_class=OtherAssetValueForm,
        template="finance/edit_other_asset_value.html",
        context_key="value",
        success_message=_("Value entry saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#values-panel",
        parent_field="asset",
    )


def delete_other_asset_value(
    request: HttpRequest, asset_pk: int, value_pk: int
) -> HttpResponse:
    """Delete a value entry of an other asset."""
    return _delete_account_related(
        request,
        account_pk=asset_pk,
        account_model=OtherAsset,
        model=OtherAssetValue,
        object_pk=value_pk,
        success_message=_("Value entry deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#values-panel",
        parent_field="asset",
    )


def _live_data_enabled(request: HttpRequest) -> bool:
    return getattr(
        request.user.profile,  # ty: ignore[unresolved-attribute]
        "live_data_enabled",
        True,
    )


@require_POST  # type: ignore
def update_other_asset_price(request: HttpRequest, pk: int) -> HttpResponse:
    """Record today's value as quantity × the live price of the market symbol."""
    asset = get_object_or_404(OtherAsset, pk=pk)
    detail_url = reverse(DETAIL_URL, kwargs={"pk": pk}) + "#values-panel"
    if not asset.has_market_price or not _live_data_enabled(request):
        messages.error(request, _("Live market data is not available for this asset."))
        return HttpResponseRedirect(detail_url)
    try:
        quote = get_live_quote(asset.ticker, force_refresh=True)
    except MarketDataError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(detail_url)
    if quote.currency != asset.currency:
        messages.error(
            request,
            _(
                "Quote currency ({quote}) differs from the asset currency "
                "({asset}); no value was recorded."
            ).format(quote=quote.currency, asset=asset.currency),
        )
        return HttpResponseRedirect(detail_url)
    assert asset.quantity is not None
    amount = (asset.quantity * quote.price).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    OtherAssetValue.objects.update_or_create(
        asset=asset,
        value_date=datetime.date.today(),
        defaults={"value": Money(amount, asset.currency)},
    )
    messages.success(
        request,
        _("Value updated to {value}.").format(value=Money(amount, asset.currency)),
    )
    return HttpResponseRedirect(detail_url)
