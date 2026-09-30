"""Views applying the yearly IRL revision of a lease rent."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from property.models import Lease
from property.services.rent_revision import apply_rent_revision, get_rent_revision


@require_POST  # type: ignore
def apply_lease_rent_revision(
    request: HttpRequest, property_pk: int, lease_pk: int
) -> HttpResponse:
    """Apply the computed IRL revision to the lease and its recurring rent entries."""
    lease = get_object_or_404(
        Lease.objects.select_related("property"), pk=lease_pk, property_id=property_pk
    )
    redirect_url = reverse("property:detail", kwargs={"pk": property_pk}) + (
        "#leases-panel"
    )
    revision = get_rent_revision(lease)
    if revision is None or revision.new_rent is None:
        messages.error(request, _("The rent revision cannot be computed."))
        return HttpResponseRedirect(redirect_url)
    if not revision.is_due:
        messages.error(request, _("The rent revision is not due yet."))
        return HttpResponseRedirect(redirect_url)
    try:
        effective_date = datetime.date.fromisoformat(
            request.POST.get("effective_date", "")
        )
    except ValueError:
        effective_date = None
    new_rent = revision.new_rent
    updated = apply_rent_revision(revision, effective_date)
    messages.success(
        request,
        _("Rent revised to {rent}; {count} recurring rent series updated.").format(
            rent=new_rent, count=updated
        ),
    )
    return HttpResponseRedirect(redirect_url)
