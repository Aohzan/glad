"""Views managing the owners of the assets and the net worth per person."""

import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from base.forms import BirthDateForm, OwnershipForm
from base.models import Ownership
from base.services.ownership import (
    ASSET_KINDS,
    kind_of,
    net_worth_by_person,
    ownerships_of,
    right_ratio,
)


def manage_owners(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    """List the owners of an asset and add or update one."""
    asset_kind = ASSET_KINDS.get(kind)
    if asset_kind is None:
        raise Http404
    asset = get_object_or_404(asset_kind.model, pk=pk)
    rows = ownerships_of(asset)
    if request.method == "POST":
        user_pk = request.POST.get("user", "")
        existing = next((r for r in rows if str(r.user_id) == user_pk), None)  # ty: ignore[unresolved-attribute]
        form = OwnershipForm(
            request.POST,
            instance=existing,
            others=[r for r in rows if r is not existing],
            dismemberable=asset_kind.dismemberable,
        )
        if form.is_valid():
            ownership = form.save(commit=False)
            ownership.content_type = ContentType.objects.get_for_model(asset)
            ownership.object_id = asset.pk
            ownership.save()
            messages.success(request, _("Owner saved."))
            return redirect("manage_owners", kind=kind, pk=pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = OwnershipForm(others=rows, dismemberable=asset_kind.dismemberable)
    today = datetime.date.today()
    return render(
        request,
        "owners_manage.html",
        {
            "asset": asset,
            "kind": asset_kind,
            "back_url": asset_kind.detail_url(asset),
            "rows": [{"obj": r, "ratio": right_ratio(r, today)} for r in rows],
            "form": form,
        },
    )


@require_POST  # type: ignore
def delete_ownership(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove an owner from an asset."""
    ownership = get_object_or_404(Ownership, pk=pk)
    asset = ownership.asset
    ownership.delete()
    messages.success(request, _("Owner removed."))
    if asset is None:
        return redirect("owners")
    return redirect("manage_owners", kind=kind_of(asset), pk=asset.pk)


def owners_overview(request: HttpRequest) -> HttpResponse:
    """Net worth of each household member, and the birth date of the user."""
    profile = request.user.profile  # ty: ignore[unresolved-attribute]
    if request.method == "POST":
        birth_form = BirthDateForm(request.POST)
        if birth_form.is_valid():
            profile.birth_date = birth_form.cleaned_data["birth_date"]
            profile.save(update_fields=["birth_date"])
            messages.success(request, _("Birth date saved."))
            return redirect("owners")
    else:
        birth_form = BirthDateForm(initial={"birth_date": profile.birth_date})
    people, unassigned, outside = net_worth_by_person()
    return render(
        request,
        "owners.html",
        {
            "people": people,
            "unassigned": unassigned,
            "outside": outside,
            "kinds": ASSET_KINDS,
            "currency": settings.DEFAULT_CURRENCY,
            "birth_form": birth_form,
        },
    )
