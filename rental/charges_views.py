"""Views of the yearly charges reconciliation of a lease."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from property.models import Lease
from rental.models import ChargesReconciliation
from rental.parsing import parse_amount, parse_date, parse_lines
from rental.services import charges
from rental.services.payments import first_due_date
from rental.views import get_lease, lease_context

#: Empty adjustment rows offered on the reconciliation form.
EMPTY_ADJUSTMENTS = 2


def lease_charges(request: HttpRequest, pk: int) -> HttpResponse:
    """The reconciliations of a lease, and a new one."""
    lease = get_lease(pk)
    start, end = charges.default_period(lease, datetime.date.today())
    return render(
        request,
        "rental/lease_charges.html",
        {
            **lease_context(lease, "charges"),
            "reconciliations": lease.charges_reconciliations.all(),  # ty: ignore[unresolved-attribute]
            "default_start": start,
            "default_end": end,
            "is_provision": lease.charges_mode == Lease.ChargesMode.PROVISION,
        },
    )


@require_POST  # type: ignore
def create_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    lease = get_lease(pk)
    start = parse_date(request.POST.get("period_start"))
    end = parse_date(request.POST.get("period_end"))
    if start is None or end is None or start > end:
        messages.error(request, _("Enter a valid period."))
        return redirect("rental:lease_charges", pk=lease.pk)
    reconciliation = charges.create(lease, start, end)
    return redirect("rental:reconciliation_detail", pk=reconciliation.pk)


def _reconciliation(pk: int) -> ChargesReconciliation:
    return get_object_or_404(
        ChargesReconciliation.objects.select_related("lease__property"), pk=pk
    )


def reconciliation_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Provisions, expenses and adjustments of a reconciliation, and its balance."""
    reconciliation = _reconciliation(pk)
    lease = get_lease(reconciliation.lease_id)
    if (
        request.method == "POST"
        and reconciliation.status == ChargesReconciliation.Status.DRAFT
    ):
        adjustments = parse_lines(request, "adjustment")
        if adjustments is None:
            messages.error(request, _("Each adjustment needs a label and an amount."))
        else:
            reconciliation.adjustments = adjustments
            reconciliation.save(update_fields=["adjustments", "updated_at"])
            if request.POST.get("action") == "refresh":
                charges.compute(reconciliation)
            messages.success(request, _("Reconciliation saved."))
            return redirect("rental:reconciliation_detail", pk=reconciliation.pk)
    today = datetime.date.today()
    return render(
        request,
        "rental/reconciliation_detail.html",
        {
            **lease_context(lease, "charges"),
            "reconciliation": reconciliation,
            "balance_abs": abs(reconciliation.balance),
            "editable": reconciliation.status == ChargesReconciliation.Status.DRAFT,
            "empty_rows": range(EMPTY_ADJUSTMENTS),
            "ratio": charges.occupancy_ratio(
                lease, reconciliation.period_start, reconciliation.period_end
            ),
            "suggested": charges.suggested_provision(reconciliation),
            "effective_date": max(first_due_date(lease), today.replace(day=1)),
        },
    )


def reconciliation_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    reconciliation = _reconciliation(pk)
    response = HttpResponse(
        charges.statement_pdf(reconciliation), content_type="application/pdf"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="regularisation-charges-{reconciliation.period_end:%Y}.pdf"'
    )
    return response


@require_POST  # type: ignore
def record_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """Record the balance in the ledger of the property."""
    reconciliation = _reconciliation(pk)
    if charges.record_balance(reconciliation) is not None:
        messages.success(request, _("Balance recorded in the ledger of the property."))
    return redirect("rental:reconciliation_detail", pk=reconciliation.pk)


@require_POST  # type: ignore
def update_provision(request: HttpRequest, pk: int) -> HttpResponse:
    """Change the monthly provision of the lease from a date."""
    reconciliation = _reconciliation(pk)
    amount = parse_amount(request.POST.get("amount"))
    effective_date = parse_date(request.POST.get("effective_date"))
    if amount is None or amount < 0 or effective_date is None:
        messages.error(request, _("Enter a valid amount and date."))
    else:
        updated = charges.update_provision(reconciliation.lease, amount, effective_date)
        messages.success(
            request,
            _("Provision updated; %(count)d recurring charges series updated.")
            % {"count": updated},
        )
    return redirect("rental:reconciliation_detail", pk=reconciliation.pk)


@require_POST  # type: ignore
def delete_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    reconciliation = _reconciliation(pk)
    lease_pk = reconciliation.lease_id
    if reconciliation.status == ChargesReconciliation.Status.DRAFT:
        reconciliation.delete()
        messages.success(request, _("Reconciliation deleted."))
    return redirect("rental:lease_charges", pk=lease_pk)
