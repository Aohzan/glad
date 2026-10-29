"""Views of the departure of a tenant: notice, deposit return and closing."""

import datetime
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rental import rules
from rental.models import DepositSettlement, Inventory
from rental.parsing import parse_amount, parse_date, parse_lines
from rental.services import departure
from rental.views import get_lease, lease_context

#: Empty deduction rows offered on the deposit form.
EMPTY_DEDUCTIONS = 2


def lease_departure(request: HttpRequest, pk: int) -> HttpResponse:
    """Notice, exit inventory, deposit return and closing of a lease."""
    lease = get_lease(pk)
    today = datetime.date.today()
    settlement = DepositSettlement.objects.filter(lease=lease).first()
    comparison = departure.compare(lease)
    context = {
        **lease_context(lease, "departure"),
        "today": today,
        "tenant_notice_months": rules.tenant_notice_months(lease),
        "landlord_deadline": departure.landlord_notice_deadline(lease, today),
        "term_end": rules.term_end(lease, today),
        "exit_inventory": Inventory.objects.filter(
            lease=lease, kind=Inventory.Kind.EXIT
        ).first(),
        "worse": [row for row in comparison if row.is_worse],
        "compared": bool(comparison),
        "settlement": settlement,
        "empty_rows": range(EMPTY_DEDUCTIONS),
        "withholding_max": (
            lease.deposit_amount.amount * rules.COOWNERSHIP_WITHHOLDING_MAX
        ).quantize(Decimal("0.01")),
    }
    if settlement is not None:
        on = settlement.returned_date or today
        context.update(
            {
                "deadline": departure.return_deadline(settlement),
                "penalty": departure.penalty(settlement, on),
                "to_pay": departure.to_pay(settlement, on),
            }
        )
    return render(request, "rental/lease_departure.html", context)


@require_POST  # type: ignore
def give_notice(request: HttpRequest, pk: int) -> HttpResponse:
    lease = get_lease(pk)
    notice_date = parse_date(request.POST.get("notice_date"))
    by = request.POST.get("notice_by")
    if notice_date is None or by not in (departure.TENANT, departure.LANDLORD):
        messages.error(request, _("Enter the date of the notice and who gave it."))
    else:
        departure.give_notice(lease, notice_date, by)
        messages.success(
            request,
            _("Notice recorded: the lease ends on %(date)s.")
            % {"date": lease.end_date},
        )
    return redirect("rental:lease_departure", pk=lease.pk)


@require_POST  # type: ignore
def save_settlement(request: HttpRequest, pk: int) -> HttpResponse:
    """The keys returned, the amounts kept and the share withheld."""
    lease = get_lease(pk)
    settlement = DepositSettlement.objects.filter(lease=lease).first()
    if (
        settlement is not None
        and settlement.status == DepositSettlement.Status.RETURNED
    ):
        return redirect("rental:lease_departure", pk=lease.pk)
    keys_date = parse_date(request.POST.get("keys_returned_date"))
    deductions = parse_lines(request, "deduction")
    withholding = parse_amount(request.POST.get("coownership_withholding") or "0")
    maximum = lease.deposit_amount.amount * rules.COOWNERSHIP_WITHHOLDING_MAX
    if (
        keys_date is None
        or deductions is None
        or withholding is None
        or not 0 <= withholding <= maximum
    ):
        messages.error(
            request,
            _(
                "Enter the date the keys were returned, a label and an amount for "
                "each deduction, and keep at most 20 % of the deposit."
            ),
        )
        return redirect("rental:lease_departure", pk=lease.pk)
    DepositSettlement.objects.update_or_create(
        lease=lease,
        defaults={
            "keys_returned_date": keys_date,
            "exit_matches_entry": request.POST.get("exit_matches_entry") == "on",
            "deductions": deductions,
            "coownership_withholding": withholding,
        },
    )
    messages.success(request, _("Deposit return saved."))
    return redirect("rental:lease_departure", pk=lease.pk)


def deposit_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    lease = get_lease(pk)
    settlement = get_object_or_404(DepositSettlement, lease=lease)
    response = HttpResponse(
        departure.statement_pdf(settlement), content_type="application/pdf"
    )
    response["Content-Disposition"] = (
        'attachment; filename="restitution-depot-de-garantie.pdf"'
    )
    return response


@require_POST  # type: ignore
def return_deposit(request: HttpRequest, pk: int) -> HttpResponse:
    """The deposit is paid back: record it in the ledger."""
    lease = get_lease(pk)
    settlement = get_object_or_404(
        DepositSettlement, lease=lease, status=DepositSettlement.Status.DRAFT
    )
    returned = parse_date(request.POST.get("returned_date")) or datetime.date.today()
    departure.settle(settlement, returned)
    messages.success(request, _("Deposit return recorded in the ledger."))
    return redirect("rental:lease_departure", pk=lease.pk)


@require_POST  # type: ignore
def close_lease(request: HttpRequest, pk: int) -> HttpResponse:
    """End the lease and stop its recurring rent and charges."""
    lease = get_lease(pk)
    end_date = parse_date(request.POST.get("end_date"))
    if end_date is None or end_date < lease.start_date:
        messages.error(request, _("Enter a valid end date."))
        return redirect("rental:lease_departure", pk=lease.pk)
    ended = departure.close_lease(lease, end_date)
    messages.success(
        request,
        _("Lease closed; %(count)d recurring series ended.") % {"count": ended},
    )
    return redirect("rental:lease_detail", pk=lease.pk)
