"""Notification types of the self-managed leases."""

import datetime
from collections.abc import Iterator
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from base.models import Document
from base.services.pdf import money
from notifications.checks import days_before_param, month_day, when
from notifications.registry import Event, NotificationType, Param, register
from property.models import Lease, Property
from rental.models import (
    ChargesReconciliation,
    SignatureRequest,
)
from rental.services.compliance import MISSING, documents_by_lease, lease_checks
from rental.services.dashboard import current_leases
from rental.services.payments import lease_periods

#: A missing item of a lease checklist is notified again after this many days.
COMPLIANCE_RENOTIFY_DAYS = 30


def _self_managed(today: datetime.date) -> list[Lease]:
    return [lease for lease in current_leases() if lease.mandate_on(today) is None]


def _title(lease: Lease) -> str:
    return f"{lease.property.name} — {lease.name or _('Lease')}"


def _compliance_issues(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    leases = _self_managed(today)
    documents = documents_by_lease(leases)
    for lease in leases:
        missing = [
            check
            for check in lease_checks(lease, documents[lease.pk], today)
            if check.status == MISSING
        ]
        if not missing:
            continue
        yield Event(
            key=f"{lease.pk}:{','.join(sorted(check.key for check in missing))}",
            title=ngettext(
                "%(lease)s: %(count)d item missing",
                "%(lease)s: %(count)d items missing",
                len(missing),
            )
            % {"lease": _title(lease), "count": len(missing)},
            body="\n".join(f"{check.label}: {check.detail}" for check in missing),
            url=reverse("rental:lease_detail", kwargs={"pk": lease.pk}),
            level="warning",
        )


def _tenant_insurance(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    leases = [
        lease
        for lease in _self_managed(today)
        if lease.status != Lease.Status.UPCOMING
        and lease.lease_type != Lease.LeaseType.MOBILITY
    ]
    documents = documents_by_lease(leases)
    for lease in leases:
        dated = [
            d.valid_until
            for d in documents[lease.pk].of_kind(Document.Kind.INSURANCE)
            if d.valid_until
        ]
        if not dated:
            continue
        valid_until = max(dated)
        if (valid_until - today).days > params["days_before"]:
            continue
        yield Event(
            key=f"{lease.pk}:{valid_until.isoformat()}",
            title=(
                _("Tenant insurance expired: %(lease)s")
                if valid_until < today
                else _("Tenant insurance expires soon: %(lease)s")
            )
            % {"lease": _title(lease)},
            body=when(valid_until, today),
            url=reverse("rental:lease_documents", kwargs={"pk": lease.pk}),
            level="warning",
        )


def _diagnostic_expiry(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    rented = {lease.property.pk: lease for lease in _self_managed(today)}
    diagnostics = Document.objects.filter(
        content_type=ContentType.objects.get_for_model(Property),
        object_id__in=rented,
        kind=Document.Kind.DIAGNOSTIC,
        valid_until__isnull=False,
        valid_until__lte=today + datetime.timedelta(days=params["days_before"]),
    )
    for document in diagnostics:
        lease = rented[document.object_id]
        assert document.valid_until is not None
        yield Event(
            key=f"{document.pk}:{document.valid_until.isoformat()}",
            title=_("Diagnostic to renew: %(title)s — %(property)s")
            % {"title": document.title, "property": lease.property.name},
            body=when(document.valid_until, today),
            url=reverse("rental:lease_documents", kwargs={"pk": lease.pk}),
            level="warning",
        )


def _rent_late(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    for lease in _self_managed(today):
        if lease.status == Lease.Status.UPCOMING:
            continue
        for period in lease_periods(lease, today):
            if period.days_late < params["days"]:
                continue
            yield Event(
                key=f"{lease.pk}:{period.key}",
                title=_("Rent of %(month)s not received: %(lease)s")
                % {"month": period.key, "lease": _title(lease)},
                body=_("%(amount)s still due.") % {"amount": money(period.balance)}
                + " "
                + when(period.due_date or today, today),
                url=reverse("rental:lease_payments", kwargs={"pk": lease.pk}),
                level="warning",
            )


def _signature_pending(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    pending = SignatureRequest.objects.filter(
        status=SignatureRequest.Status.PENDING,
        created_at__date__lte=today - datetime.timedelta(days=params["days"]),
    )
    for signature in pending:
        waiting = [s["name"] for s in signature.signers if s.get("status") != "signed"]
        yield Event(
            key=str(signature.pk),
            title=_("Still to sign: %(title)s") % {"title": signature.title},
            body=_("Waiting for %(names)s.") % {"names": ", ".join(waiting)},
            url=reverse("rental:dashboard"),
            level="warning",
        )


def _charges_due(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    """Leases with provisions whose last year is not reconciled yet."""
    if today < month_day(params["date"], today.year):
        return
    year_end = datetime.date(today.year - 1, 12, 31)
    for lease in _self_managed(today):
        if (
            lease.charges_mode != Lease.ChargesMode.PROVISION
            or lease.start_date > year_end
            or ChargesReconciliation.objects.filter(
                lease=lease, period_end__gte=year_end.replace(day=1)
            ).exists()
        ):
            continue
        yield Event(
            key=f"{lease.pk}:{year_end.year}",
            title=_("Reconcile the charges of %(year)d: %(lease)s")
            % {"year": year_end.year, "lease": _title(lease)},
            url=reverse("rental:lease_charges", kwargs={"pk": lease.pk}),
        )


register(
    NotificationType(
        key="charges_reconciliation_due",
        group="rental",
        label=gettext_lazy("Charges reconciliation"),
        description=gettext_lazy(
            "The charges provisions of the last year of a lease are still to "
            "reconcile with the actual expenses."
        ),
        check=_charges_due,
        params=(
            Param(
                "date",
                gettext_lazy("From"),
                "03-01",
                kind="monthday",
                help_text=gettext_lazy("Date of the reminder each year (MM-DD)."),
            ),
        ),
    )
)
register(
    NotificationType(
        key="signature_completed",
        group="rental",
        label=gettext_lazy("Document signed"),
        description=gettext_lazy(
            "Everyone signed a lease or an inventory sent for electronic signature."
        ),
    )
)
register(
    NotificationType(
        key="signature_pending",
        group="rental",
        label=gettext_lazy("Signature pending"),
        description=gettext_lazy(
            "A document sent for electronic signature is still not signed by "
            "everyone after some days."
        ),
        check=_signature_pending,
        params=(
            Param(
                "days",
                gettext_lazy("Days after the sending"),
                7,
                min_value=1,
                max_value=60,
            ),
        ),
        renotify_days=7,
    )
)
register(
    NotificationType(
        key="rent_late",
        group="rental",
        label=gettext_lazy("Late rent"),
        description=gettext_lazy(
            "The rent of a lease you manage yourself is not checked as received "
            "some days after its due date."
        ),
        check=_rent_late,
        params=(
            Param(
                "days",
                gettext_lazy("Days after the due date"),
                5,
                min_value=0,
                max_value=60,
            ),
        ),
    )
)
register(
    NotificationType(
        key="compliance_issue",
        group="rental",
        label=gettext_lazy("Lease checklist"),
        description=gettext_lazy(
            "A document or a piece of information required by the law is "
            "missing from a lease you manage yourself."
        ),
        check=_compliance_issues,
        renotify_days=COMPLIANCE_RENOTIFY_DAYS,
    )
)
register(
    NotificationType(
        key="tenant_insurance",
        group="rental",
        label=gettext_lazy("Tenant insurance"),
        description=gettext_lazy(
            "The home insurance certificate of a tenant expires: ask for the new one."
        ),
        check=_tenant_insurance,
        params=(days_before_param(30),),
    )
)
register(
    NotificationType(
        key="diagnostic_expiry",
        group="rental",
        label=gettext_lazy("Diagnostics"),
        description=gettext_lazy(
            "A diagnostic of a rented property expires (electricity, gas, risks…)."
        ),
        check=_diagnostic_expiry,
        params=(days_before_param(60),),
    )
)
