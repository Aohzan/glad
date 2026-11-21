"""Views managing the owners of the assets and the net worth per person."""

import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.forms import can_edit_member
from base.forms import OwnershipForm
from base.models import Ownership, display_name
from base.services.ownership import (
    ASSET_KINDS,
    kind_of,
    missing_birth_dates,
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
        existing = next((r for r in rows if str(r.user_id) == user_pk), None)
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
        # The edit button of a row prefills the form with that owner.
        user_pk = request.GET.get("user", "")
        existing = next((r for r in rows if str(r.user_id) == user_pk), None)
        form = OwnershipForm(
            instance=existing,
            others=[r for r in rows if r is not existing],
            dismemberable=asset_kind.dismemberable,
        )
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
    """Net worth of each household member."""
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
            "missing_birth_dates": [
                {
                    "name": display_name(user),
                    "edit_url": reverse("accounts:household_edit", args=[user.pk])
                    if can_edit_member(request.user, user)
                    else "",
                }
                for user in missing_birth_dates()
            ],
        },
    )
