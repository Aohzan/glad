"""Views of the rental management: dashboard and lease pages."""

import datetime

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from base.models import Document
from base.services.deadlines import PAST_DAYS, deadlines_of
from base.services.documents import documents_of
from base.services.mailer import can_send_emails
from property.forms import LeasePartyForm
from property.models import Lease, LeaseParty
from rental import emails, rules
from rental.forms import DocumentUploadForm, LeaseEmailForm
from rental.models import (
    Inventory,
    SignatureRequest,
)
from rental.services.applications import open_applications
from rental.services.compliance import issues, lease_checks
from rental.services.dashboard import lease_rows, monthly_rent_roll, occupancy_rate
from rental.services.documenso import is_configured
from rental.services.landlord import landlord_of
from rental.services.move_in import move_in_steps
from rental.services.payments import (
    Period,
    arrears,
    create_rent_schedule,
    first_due_date,
    has_schedule,
    lease_periods,
    summarize,
)
from rental.services.receipts import receipt_for, receipt_pdf
from rental.services.sending import emails_of, send_lease_email
from rental.uploads import store_upload

#: Deadline kinds shown on the rental dashboard.
RENTAL_DEADLINES = {
    "rent_revision",
    "lease_end",
    "dpe_ban",
    "dpe_expiry",
}
#: Rental deadlines are shown this many days in advance.
DEADLINES_AHEAD_DAYS = 180
#: The move-in steps are shown until this long after the start of the lease.
MOVE_IN_DAYS = datetime.timedelta(days=90)


def dashboard(request: HttpRequest) -> HttpResponse:
    """Leases followed by the household, their compliance and their deadlines."""
    today = datetime.date.today()
    rows = lease_rows(today)
    self_managed = [row for row in rows if row.mandate is None]
    deadlines = [
        d
        for d in deadlines_of(RENTAL_DEADLINES, today)
        if -PAST_DAYS <= d.days_left <= DEADLINES_AHEAD_DAYS
    ]
    return render(
        request,
        "rental/dashboard.html",
        {
            "today": today,
            "self_managed": self_managed,
            "managed": [row for row in rows if row.mandate is not None],
            "running_count": sum(
                row.lease.status != Lease.Status.UPCOMING for row in self_managed
            ),
            "upcoming_count": sum(
                row.lease.status == Lease.Status.UPCOMING for row in self_managed
            ),
            "rent_roll": monthly_rent_roll(row.lease for row in self_managed),
            "occupancy": occupancy_rate(today),
            "payments": summarize(
                {row.lease.pk: row.periods for row in self_managed}, today
            ),
            "issue_rows": [row for row in self_managed if row.issues],
            "issue_count": sum(len(row.issues) for row in self_managed),
            "deadlines": deadlines,
            "applications": open_applications(),
            "pending_signatures": SignatureRequest.objects.filter(
                status=SignatureRequest.Status.PENDING
            ),
        },
    )


def get_lease(pk: int) -> Lease:
    return get_object_or_404(
        Lease.objects.select_related("property").prefetch_related(
            "parties", "property__mandates", "property__ownerships__user__profile"
        ),
        pk=pk,
    )


def signatures_of(lease: Lease):
    """Signature requests of the lease and of its inventories."""
    return SignatureRequest.objects.filter(
        Q(content_type=ContentType.objects.get_for_model(Lease), object_id=lease.pk)
        | Q(
            content_type=ContentType.objects.get_for_model(Inventory),
            object_id__in=Inventory.objects.filter(lease=lease).values("pk"),
        )
    )


def lease_context(lease: Lease, tab: str) -> dict:
    return {"lease": lease, "tab": tab, "mandate": lease.mandate_on()}


def lease_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Summary of a lease: parties, conditions, landlord and checklist."""
    lease = get_lease(pk)
    checks = lease_checks(lease)
    steps = move_in_steps(lease, checks)
    return render(
        request,
        "rental/lease_detail.html",
        {
            **lease_context(lease, "summary"),
            "checks": checks,
            "issue_count": len(issues(checks)),
            "landlord": landlord_of(lease.property),
            "deposit_cap": rules.deposit_cap(lease),
            "legal_duration": rules.DEFAULT_DURATION_MONTHS.get(lease.lease_type),
            "steps": steps,
            "show_steps": lease.start_date >= datetime.date.today() - MOVE_IN_DAYS
            and not all(step.done for step in steps),
            "signatures": signatures_of(lease),
            "can_sign": is_configured(),
        },
    )


def _documents_page(
    request: HttpRequest, lease: Lease, form: DocumentUploadForm, status: int = 200
) -> HttpResponse:
    return render(
        request,
        "rental/lease_documents.html",
        {
            **lease_context(lease, "documents"),
            "form": form,
            "lease_documents": documents_of(lease),
            "property_documents": documents_of(lease.property).filter(
                kind=Document.Kind.DIAGNOSTIC
            ),
        },
        status=status,
    )


def lease_documents(request: HttpRequest, pk: int) -> HttpResponse:
    """Documents of a lease and diagnostics of its property."""
    return _documents_page(request, get_lease(pk), DocumentUploadForm())


@require_POST  # type: ignore
def upload_lease_document(request: HttpRequest, pk: int) -> HttpResponse:
    """Store a document of a lease; a diagnostic goes to the property."""
    lease = get_lease(pk)
    form = DocumentUploadForm(request.POST, request.FILES)
    if store_upload(
        request,
        form,
        lambda kind: lease.property if kind == Document.Kind.DIAGNOSTIC else lease,
    ):
        return redirect("rental:lease_documents", pk=lease.pk)
    return _documents_page(request, lease, form, status=400)


def edit_party(
    request: HttpRequest, lease_pk: int, pk: int | None = None
) -> HttpResponse:
    """Add or edit a tenant or a guarantor of a lease."""
    lease = get_lease(lease_pk)
    party = get_object_or_404(LeaseParty, pk=pk, lease=lease) if pk else None
    if request.method == "POST":
        form = LeasePartyForm(request.POST, instance=party)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.lease = lease
            saved.save()
            messages.success(request, _("%(name)s saved.") % {"name": saved.name})
            return redirect("rental:lease_detail", pk=lease.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        initial = {}
        if party is None and request.GET.get("role") in LeaseParty.Role.values:
            initial["role"] = request.GET["role"]
        form = LeasePartyForm(instance=party, initial=initial)
    return render(
        request,
        "rental/edit_party.html",
        {"lease": lease, "party": party, "form": form},
    )


@require_POST  # type: ignore
def delete_party(request: HttpRequest, lease_pk: int, pk: int) -> HttpResponse:
    """Remove a tenant or a guarantor from a lease."""
    party = get_object_or_404(LeaseParty, pk=pk, lease_id=lease_pk)
    party.delete()
    messages.success(request, _("%(name)s removed.") % {"name": party.name})
    return redirect("rental:lease_detail", pk=lease_pk)


def lease_payments(request: HttpRequest, pk: int) -> HttpResponse:
    """Rent due and received for each period of a lease."""
    lease = get_lease(pk)
    periods = lease_periods(lease)
    receipts = {receipt.period_start: receipt for receipt in lease.receipts.all()}  # ty: ignore[unresolved-attribute]
    return render(
        request,
        "rental/lease_payments.html",
        {
            **lease_context(lease, "payments"),
            "rows": [(period, receipts.get(period.start)) for period in periods],
            "arrears": arrears(periods),
            "has_schedule": has_schedule(lease),
            "first_due_date": first_due_date(lease),
            "checks_url": reverse("property:checks") + f"?property={lease.property.pk}",
        },
    )


@require_POST  # type: ignore
def create_schedule(request: HttpRequest, pk: int) -> HttpResponse:
    """Create the recurring rent and charges entries of a lease."""
    lease = get_lease(pk)
    if has_schedule(lease):
        messages.warning(request, _("This lease already has a rent schedule."))
    else:
        create_rent_schedule(lease)
        messages.success(request, _("Rent schedule created."))
    return redirect("rental:lease_payments", pk=lease.pk)


def _period(periods: list[Period], key: str | None) -> Period:
    period = next((p for p in periods if p.key == key), None)
    if period is None:
        raise Http404(_("Unknown period."))
    return period


def download_receipt(request: HttpRequest, pk: int, period: str) -> HttpResponse:
    """The receipt of a paid (or partly paid) period, as a PDF."""
    lease = get_lease(pk)
    selected = _period(lease_periods(lease), period)
    if not selected.paid:
        raise Http404(_("Nothing was received for this period."))
    receipt = receipt_for(lease, selected)
    response = HttpResponse(receipt_pdf(receipt), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{receipt.filename}"'
    return response


def compose_email(request: HttpRequest, pk: int, kind: str) -> HttpResponse:
    """Prepare an email to the tenants, to check and edit before sending it."""
    lease = get_lease(pk)
    email_kind = emails.KINDS.get(kind)
    if email_kind is None:
        raise Http404(_("Unknown email."))
    periods = lease_periods(lease)
    period = None
    if email_kind.needs_period:
        period = _period(
            periods, request.POST.get("period") or request.GET.get("period")
        )
    if email_kind.key == emails.RECEIPT and period is not None and not period.paid:
        raise Http404(_("Nothing was received for this period."))
    if request.method == "POST":
        form = LeaseEmailForm(request.POST)
        if form.is_valid():
            send_lease_email(
                lease,
                email_kind,
                to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                period=period,
                user=request.user,
            )
            messages.success(request, _("The email is being sent."))
            return redirect("rental:lease_emails", pk=lease.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        subject, body = emails.render(
            email_kind,
            lease,
            periods,
            period,
        )
        form = LeaseEmailForm(
            initial={
                "to": ", ".join(emails.recipients(lease)),
                "cc": ", ".join(emails.copies(lease, email_kind)),
                "subject": subject,
                "body": body,
            }
        )
    attachment = None
    if email_kind.key == emails.RECEIPT and period is not None:
        attachment = "quittance" if period.paid >= period.expected else "recu"
        attachment = f"{attachment}-{period.key}.pdf"
    return render(
        request,
        "rental/compose_email.html",
        {
            **lease_context(lease, "emails"),
            "kind": email_kind,
            "period": period,
            "form": form,
            "attachment": attachment,
            "can_send": can_send_emails(),
        },
    )


def lease_emails(request: HttpRequest, pk: int) -> HttpResponse:
    """Emails sent to the tenants of a lease."""
    lease = get_lease(pk)
    return render(
        request,
        "rental/lease_emails.html",
        {
            **lease_context(lease, "emails"),
            "sent_emails": emails_of(lease),
            "kinds": [
                kind for kind in emails.KINDS.values() if not (kind.needs_period)
            ],
        },
    )
