"""Views recording the yearly rates credited by life insurance euro funds."""

from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from finance.forms import EuroFundRateForm
from finance.models.investment_account import EuroFundRate, InvestmentAccountHolding


def _holding_url(holding: InvestmentAccountHolding) -> str:
    return (
        reverse(
            "finance:holding_detail",
            kwargs={"account_pk": holding.account_id, "holding_pk": holding.pk},  # ty: ignore[unresolved-attribute]
        )
        + "#rates-panel"
    )


@require_POST  # type: ignore
def add_euro_fund_rate(
    request: HttpRequest, account_pk: int, holding_pk: int
) -> HttpResponse:
    """Record (or replace) the rate credited for a year."""
    holding = get_object_or_404(
        InvestmentAccountHolding, pk=holding_pk, account_id=account_pk
    )
    form = EuroFundRateForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Please correct the errors below."))
        return HttpResponseRedirect(_holding_url(holding))
    try:
        EuroFundRate.objects.update_or_create(
            holding=holding,
            year=form.cleaned_data["year"],
            defaults={
                "rate": form.cleaned_data["rate"],
                "notes": form.cleaned_data["notes"],
            },
        )
    except IntegrityError:  # pragma: no cover - concurrent insert of the same year
        messages.error(request, _("This year already has a rate."))
    else:
        messages.success(request, _("Rate saved."))
    return HttpResponseRedirect(_holding_url(holding))


@require_POST  # type: ignore
def delete_euro_fund_rate(
    request: HttpRequest, account_pk: int, holding_pk: int, rate_pk: int
) -> HttpResponse:
    """Delete a recorded rate."""
    rate = get_object_or_404(
        EuroFundRate,
        pk=rate_pk,
        holding_id=holding_pk,
        holding__account_id=account_pk,
    )
    holding = rate.holding
    rate.delete()
    messages.success(request, _("Rate deleted."))
    return HttpResponseRedirect(_holding_url(holding))
