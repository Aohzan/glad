"""Simulation of the capital gain tax when selling a property."""

import datetime
from decimal import Decimal

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from base.models import Ownership
from base.services.ownership import ownerships_of
from property.forms import ResaleSimulationForm
from property.models import Property
from property.services.capital_gain import ResaleInputs, estimate_resale


def _seller_shares(prop: Property) -> tuple[Decimal, ...]:
    """Shares of the sellers holding the full ownership, 100 % when unknown."""
    shares = tuple(
        o.share for o in ownerships_of(prop) if o.right == Ownership.Right.FULL
    )
    return shares or (Decimal(100),)


def resale_simulation(request: HttpRequest, pk: int) -> HttpResponse:
    """Estimate the capital gain, the taxes and the net proceeds of a sale."""
    prop = get_object_or_404(Property, pk=pk)
    # Without parameters the simulation runs on the current value, today.
    defaults = {
        "sale_price": prop.gross_value.amount,
        "sale_date": datetime.date.today(),
    }
    form = ResaleSimulationForm(request.GET or defaults)
    estimate = None
    if form.is_valid():
        data = form.cleaned_data
        estimate = estimate_resale(
            prop,
            ResaleInputs(
                sale_price=data["sale_price"],
                sale_date=data["sale_date"],
                seller_fees=data["seller_fees"] or Decimal(0),
                actual_works=data["actual_works"] or Decimal(0),
                main_residence=data["main_residence"],
                service_residence=data["service_residence"],
                seller_shares=_seller_shares(prop),
            ),
        )
    return render(
        request,
        "property/resale_simulation.html",
        {"property": prop, "form": form, "estimate": estimate},
    )
