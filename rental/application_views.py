"""Views of the rental applications."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from base.services.documents import documents_of
from property.forms import FirstTenantForm, LeaseForm
from property.models import Lease
from property.views.crud_views import save_lease
from rental import rules
from rental.forms import (
    APPLICATION_DOCUMENT_KINDS,
    DocumentUploadForm,
    RentalApplicationForm,
)
from rental.models import RentalApplication
from rental.services.applications import accept
from rental.uploads import store_upload


def applications(request: HttpRequest) -> HttpResponse:
    """The open applications, then the decided ones."""
    every = RentalApplication.objects.select_related("property")
    return render(
        request,
        "rental/applications.html",
        {
            "open": [a for a in every if a.is_open],
            "closed": [a for a in every if not a.is_open],
            "effort_rate_max": rules.EFFORT_RATE_MAX,
        },
    )


def edit_application(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Record or edit a candidate."""
    application = get_object_or_404(RentalApplication, pk=pk) if pk else None
    if request.method == "POST":
        form = RentalApplicationForm(request.POST, instance=application)
        if form.is_valid():
            saved = form.save()
            messages.success(request, _("Application saved."))
            return redirect("rental:application_detail", pk=saved.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        initial = {}
        if request.GET.get("property", "").isdigit():
            initial["property"] = int(request.GET["property"])
        form = RentalApplicationForm(instance=application, initial=initial)
    return render(
        request,
        "rental/edit_application.html",
        {"application": application, "form": form},
    )


def _detail_page(
    request: HttpRequest,
    application: RentalApplication,
    upload_form: DocumentUploadForm,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "rental/application_detail.html",
        {
            "application": application,
            "documents": documents_of(application),
            "form": upload_form,
            "allowed": rules.ALLOWED_APPLICATION_DOCUMENTS,
            "forbidden": rules.FORBIDDEN_APPLICATION_DOCUMENTS,
            "effort_rate_max": rules.EFFORT_RATE_MAX,
            "actions": [
                (RentalApplication.Status.NEW, _("Reopen")),
                (RentalApplication.Status.REVIEWING, _("Review")),
                (RentalApplication.Status.REJECTED, _("Reject")),
            ],
        },
        status=status,
    )


def application_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """A candidate, the documents of the application and the decision."""
    application = get_object_or_404(
        RentalApplication.objects.select_related("property"), pk=pk
    )
    return _detail_page(
        request, application, DocumentUploadForm(kinds=APPLICATION_DOCUMENT_KINDS)
    )


@require_POST  # type: ignore
def upload_application_document(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(RentalApplication, pk=pk)
    form = DocumentUploadForm(
        request.POST, request.FILES, kinds=APPLICATION_DOCUMENT_KINDS
    )
    if store_upload(request, form, lambda kind: application):
        return redirect("rental:application_detail", pk=application.pk)
    return _detail_page(request, application, form, status=400)


@require_POST  # type: ignore
def set_application_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Put an open application under review, reject it or reopen it."""
    application = get_object_or_404(RentalApplication, pk=pk)
    status = request.POST.get("status")
    if (
        status in RentalApplication.Status.values
        and status != RentalApplication.Status.ACCEPTED
        and application.status != RentalApplication.Status.ACCEPTED
    ):
        application.status = status
        application.save(update_fields=["status", "updated_at"])
        messages.success(request, _("Application updated."))
    return redirect("rental:application_detail", pk=application.pk)


def _lease_initial(application: RentalApplication) -> dict:
    """Conditions of the new lease, from the last lease of the property."""
    previous = Lease.objects.filter(property=application.property).first()
    initial: dict = {
        "start_date": datetime.date.today(),
        "status": Lease.Status.UPCOMING,
    }
    if previous is not None:
        for name in (
            "lease_type",
            "rent_amount",
            "charges_amount",
            "charges_mode",
            "deposit_amount",
            "periodicity",
            "payment_day",
        ):
            initial[name] = getattr(previous, name)
    return initial


def accept_application(request: HttpRequest, pk: int) -> HttpResponse:
    """Accept a candidate: the lease form, with the candidate as the tenant."""
    application = get_object_or_404(
        RentalApplication.objects.select_related("property"),
        pk=pk,
        status__in=RentalApplication.OPEN_STATUSES,
    )
    prop = application.property
    if request.method == "POST":
        form = LeaseForm(request.POST)
        tenant_form = FirstTenantForm(request.POST, prefix="tenant")
        if form.is_valid() and tenant_form.is_valid():
            lease = save_lease(prop, form, tenant_form)
            accept(
                application,
                lease,
                reject_others=request.POST.get("reject_others") == "on",
            )
            messages.success(
                request, _("Lease created for %(name)s.") % {"name": application.name}
            )
            return redirect("rental:lease_detail", pk=lease.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = LeaseForm(initial=_lease_initial(application))
        tenant_form = FirstTenantForm(
            prefix="tenant",
            initial={
                "first_name": application.first_name,
                "last_name": application.last_name,
                "email": application.email,
                "phone": application.phone,
            },
        )
    return render(
        request,
        "property/edit_lease.html",
        {
            "property": prop,
            "lease": None,
            "form": form,
            "tenant_form": tenant_form,
            "application": application,
        },
    )
