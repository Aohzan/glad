"""Legal checklist of a lease: documents, diagnostics, deposit, identities.

Each check has a status like the LMNP checklist: ``ok``, ``warning`` (to do
soon or recommended), ``missing`` (required and absent) or ``na``.
"""

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from base.models import Document
from base.templatetags.format_money import format_money_filter as format_money
from property.models import Lease, Property
from property.services.energy import get_dpe_status
from rental import rules
from rental.models import Inventory
from rental.services.landlord import landlord_of

#: An insurance certificate expiring within this many days is flagged.
INSURANCE_WARNING_DAYS = 30

OK = "ok"
WARNING = "warning"
MISSING = "missing"
NA = "na"


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    status: str
    detail: str = ""
    url: str = ""

    @property
    def is_issue(self) -> bool:
        return self.status in (WARNING, MISSING)


@dataclass
class LeaseDocuments:
    """Documents of a lease and of its property."""

    lease: list[Document]
    property: list[Document]

    def of_kind(self, kind: str, *, on_property: bool = False) -> list[Document]:
        documents = self.property if on_property else self.lease
        return [d for d in documents if d.kind == kind]


def documents_by_lease(leases: Iterable[Lease]) -> dict[int, LeaseDocuments]:
    """Documents of each lease and of its property, in two queries."""
    leases = list(leases)
    by_object: dict[tuple[int, int], list[Document]] = defaultdict(list)
    lease_type = ContentType.objects.get_for_model(Lease)
    property_type = ContentType.objects.get_for_model(Property)
    for content_type, ids in (
        (lease_type, {lease.pk for lease in leases}),
        (property_type, {lease.property.pk for lease in leases}),
    ):
        for document in Document.objects.filter(
            content_type=content_type, object_id__in=ids
        ):
            by_object[content_type.pk, document.object_id].append(document)
    return {
        lease.pk: LeaseDocuments(
            lease=by_object[lease_type.pk, lease.pk],
            property=by_object[property_type.pk, lease.property.pk],
        )
        for lease in leases
    }


def _tenants(lease: Lease) -> Check:
    label = _("Tenants")
    tenants = lease.tenants
    if not tenants:
        return Check("tenants", label, MISSING, _("No tenant recorded."))
    without_email = [t.name for t in tenants if not t.email]
    if without_email:
        return Check(
            "tenants",
            label,
            WARNING,
            _("No email address for %(names)s: nothing can be sent to them.")
            % {"names": ", ".join(without_email)},
        )
    return Check("tenants", label, OK, ", ".join(t.name for t in tenants))


def _landlord(lease: Lease) -> Check:
    label = _("Landlord identity")
    landlord = landlord_of(lease.property)
    if landlord.is_complete:
        return Check("landlord", label, OK, landlord.name)
    return Check(
        "landlord",
        label,
        WARNING,
        _(
            "The name and postal address of the landlord are written on the "
            "receipts: enter the postal address of the owners in their settings, "
            "or the landlord on the property."
        ),
        reverse("property:edit", kwargs={"pk": lease.property.pk}),
    )


def _deposit(lease: Lease) -> Check:
    label = _("Security deposit")
    cap = rules.deposit_cap(lease)
    if cap is None:
        return Check("deposit", label, NA)
    if lease.deposit_amount.amount > cap.amount:
        return Check(
            "deposit",
            label,
            MISSING,
            _("%(deposit)s exceeds the legal maximum of %(cap)s.")
            % {
                "deposit": format_money(lease.deposit_amount),
                "cap": format_money(cap),
            },
        )
    return Check(
        "deposit",
        label,
        OK,
        _("Legal maximum: %(cap)s.") % {"cap": format_money(cap)},
    )


def _dpe(lease: Lease, today: datetime.date) -> Check:
    label = _("Energy rating (DPE)")
    url = reverse("property:edit", kwargs={"pk": lease.property.pk})
    prop = lease.property
    status = get_dpe_status(prop.dpe_rating, prop.dpe_date, today)
    if status is None:
        return Check("dpe", label, MISSING, _("No DPE recorded."), url)
    if status.is_banned:
        return Check(
            "dpe",
            label,
            MISSING,
            _("Housing rated %(rating)s can no longer be rented out.")
            % {"rating": status.rating},
            url,
        )
    if status.is_expired:
        return Check("dpe", label, MISSING, _("The DPE has expired."), url)
    notes = []
    if status.ban_is_near and status.ban_date:
        notes.append(
            _("Rental ban from %(date)s.") % {"date": date_format(status.ban_date)}
        )
    if status.expires_soon and status.expires_on:
        notes.append(
            _("Expires on %(date)s.") % {"date": date_format(status.expires_on)}
        )
    if status.rent_frozen:
        notes.append(_("The rent cannot be increased."))
    if notes:
        return Check("dpe", label, WARNING, " ".join(notes), url)
    return Check("dpe", label, OK, status.rating)


def _diagnostics(
    lease: Lease, documents: LeaseDocuments, today: datetime.date, url: str
) -> Check:
    label = _("Diagnostics")
    required = ", ".join(rules.required_diagnostics(lease, today))
    diagnostics = documents.of_kind(Document.Kind.DIAGNOSTIC, on_property=True)
    if not diagnostics:
        return Check(
            "diagnostics",
            label,
            MISSING,
            _("To annex to the lease: %(list)s.") % {"list": required},
            url,
        )
    expired = [d.title for d in diagnostics if d.valid_until and d.valid_until < today]
    if expired:
        return Check(
            "diagnostics",
            label,
            WARNING,
            _("Expired: %(list)s.") % {"list": ", ".join(expired)},
            url,
        )
    return Check("diagnostics", label, OK, required)


def _insurance(
    lease: Lease, documents: LeaseDocuments, today: datetime.date, url: str
) -> Check:
    label = _("Tenant insurance")
    certificates = documents.of_kind(Document.Kind.INSURANCE)
    required = lease.lease_type != Lease.LeaseType.MOBILITY and (
        lease.status != Lease.Status.UPCOMING
    )
    if not certificates:
        return Check(
            "insurance",
            label,
            MISSING if required else WARNING,
            _("Ask the tenant for their home insurance certificate."),
            url,
        )
    dated = [d.valid_until for d in certificates if d.valid_until]
    if not dated:
        return Check(
            "insurance",
            label,
            WARNING,
            _("Enter the end of validity of the certificate."),
            url,
        )
    valid_until = max(dated)
    if valid_until < today:
        return Check(
            "insurance",
            label,
            MISSING if required else WARNING,
            _("Expired on %(date)s.") % {"date": date_format(valid_until)},
            url,
        )
    detail = _("Valid until %(date)s.") % {"date": date_format(valid_until)}
    if (valid_until - today).days <= INSURANCE_WARNING_DAYS:
        return Check("insurance", label, WARNING, detail, url)
    return Check("insurance", label, OK, detail)


def _signed_lease(lease: Lease, documents: LeaseDocuments, url: str) -> Check:
    label = _("Signed lease")
    missing = WARNING if lease.status == Lease.Status.UPCOMING else MISSING
    if lease.signed_date is None:
        edit_url = reverse(
            "property:edit_lease",
            kwargs={"property_pk": lease.property.pk, "lease_pk": lease.pk},
        )
        detail_url = reverse("rental:lease_detail", kwargs={"pk": lease.pk})
        return Check(
            "signed_lease",
            label,
            missing,
            _("Enter the signature date in the lease."),
            f"{edit_url}?next={detail_url}",
        )
    if not documents.of_kind(Document.Kind.LEASE):
        return Check("signed_lease", label, missing, _("Add the signed lease."), url)
    return Check(
        "signed_lease",
        label,
        OK,
        _("Signed on %(date)s.") % {"date": date_format(lease.signed_date)},
    )


def _entry_inventory(lease: Lease, documents: LeaseDocuments, url: str) -> Check:
    label = _("Entry inventory")
    signed = Inventory.objects.filter(
        lease=lease, kind=Inventory.Kind.ENTRY, status=Inventory.Status.SIGNED
    ).exists()
    if signed or documents.of_kind(Document.Kind.INVENTORY):
        return Check("entry_inventory", label, OK)
    if lease.status == Lease.Status.UPCOMING:
        return Check(
            "entry_inventory", label, WARNING, _("To do on the move-in day."), url
        )
    return Check("entry_inventory", label, MISSING, _("Add the signed inventory."), url)


def _guarantee(lease: Lease, documents: LeaseDocuments, url: str) -> Check:
    label = _("Guarantee")
    if not lease.guarantors:
        return Check("guarantee", label, NA)
    if documents.of_kind(Document.Kind.GUARANTEE):
        return Check(
            "guarantee", label, OK, ", ".join(g.name for g in lease.guarantors)
        )
    return Check(
        "guarantee",
        label,
        MISSING,
        _("Add the signed guarantee deed or the Visale certificate."),
        url,
    )


def lease_checks(
    lease: Lease,
    documents: LeaseDocuments | None = None,
    today: datetime.date | None = None,
) -> list[Check]:
    """Checklist of *lease*; pass *documents* to avoid the queries."""
    today = today or datetime.date.today()
    if documents is None:
        documents = documents_by_lease([lease])[lease.pk]
    documents_url = reverse("rental:lease_documents", kwargs={"pk": lease.pk})
    return [
        _tenants(lease),
        _landlord(lease),
        _signed_lease(lease, documents, documents_url),
        _entry_inventory(lease, documents, documents_url),
        _deposit(lease),
        _guarantee(lease, documents, documents_url),
        _insurance(lease, documents, today, documents_url),
        _dpe(lease, today),
        _diagnostics(lease, documents, today, documents_url),
    ]


def issues(checks: Iterable[Check]) -> list[Check]:
    return [check for check in checks if check.is_issue]
