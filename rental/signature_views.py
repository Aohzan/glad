"""Views of the lease PDF, the electronic signatures and the move-in."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rental.inventory_views import get_inventory
from rental.models import SignatureRequest
from rental.services import signature as signatures
from rental.services.documenso import DocumensoError, is_configured
from rental.services.inventories import inventory_pdf
from rental.services.lease_pdf import lease_pdf
from rental.services.move_in import deposit_entry, record_deposit
from rental.views import get_lease


def lease_download(request: HttpRequest, pk: int) -> HttpResponse:
    """The draft lease as a PDF, to read before having it signed."""
    lease = get_lease(pk)
    response = HttpResponse(lease_pdf(lease), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="bail-{lease.pk}.pdf"'
    return response


def _send(request: HttpRequest, target, title: str, pdf: bytes) -> None:
    lease = signatures.lease_of(target)
    if not is_configured():
        messages.error(request, _("No signature service is configured."))
        return
    try:
        signers = signatures.signers_of(lease, getattr(request.user, "email", ""))
        signatures.request_signature(target, title=title, pdf=pdf, signers=signers)
    except (signatures.SignatureError, DocumensoError) as exc:
        messages.error(request, str(exc))
        return
    messages.success(
        request, _("Sent for signature to %(count)d people.") % {"count": len(signers)}
    )


@require_POST  # type: ignore
def sign_lease(request: HttpRequest, pk: int) -> HttpResponse:
    lease = get_lease(pk)
    _send(request, lease, f"Bail — {lease.property.name}", lease_pdf(lease))
    return redirect("rental:lease_detail", pk=lease.pk)


@require_POST  # type: ignore
def sign_inventory(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_inventory(pk)
    kind = "d'entrée" if inventory.kind == inventory.Kind.ENTRY else "de sortie"
    _send(
        request,
        inventory,
        f"État des lieux {kind} — {inventory.lease.property.name}",
        inventory_pdf(inventory),
    )
    return redirect("rental:inventory_detail", pk=inventory.pk)


@require_POST  # type: ignore
def refresh_signature(request: HttpRequest, pk: int) -> HttpResponse:
    """Ask the provider for the state of a request right now."""
    signature = get_object_or_404(SignatureRequest, pk=pk)
    lease = signatures.lease_of(signature.target)
    if signature.status == SignatureRequest.Status.PENDING:
        try:
            signatures.refresh(signature)
        except DocumensoError as exc:
            messages.error(request, str(exc))
    return redirect("rental:lease_detail", pk=lease.pk)


@require_POST  # type: ignore
def receive_deposit(request: HttpRequest, pk: int) -> HttpResponse:
    """Record the security deposit received, in the ledger of the property."""
    lease = get_lease(pk)
    if deposit_entry(lease) is None and lease.deposit_amount.amount > 0:
        record_deposit(lease, datetime.date.today())
        messages.success(request, _("Security deposit recorded."))
    return redirect("rental:lease_detail", pk=lease.pk)
