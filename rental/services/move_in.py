"""Steps of the move-in of a tenant."""

import datetime
from dataclasses import dataclass

from django.urls import reverse
from django.utils.translation import gettext as _

from property.models import Lease, PropertyLedgerEntry
from property.models.ledger import ManagementCategory
from rental.services.compliance import OK, Check
from rental.services.payments import has_schedule

DEPOSIT_IN = ManagementCategory.DEPOSIT_IN.value


@dataclass(frozen=True)
class Step:
    label: str
    done: bool
    url: str = ""


def deposit_entry(lease: Lease) -> PropertyLedgerEntry | None:
    return PropertyLedgerEntry.objects.filter(
        lease=lease, management_category=DEPOSIT_IN
    ).first()


def record_deposit(lease: Lease, date: datetime.date) -> PropertyLedgerEntry:
    """The security deposit received, as an income of the ledger."""
    return PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=DEPOSIT_IN,
        amount=lease.deposit_amount,
        entry_date=date,
        third_party=lease.name,
        description=_("Security deposit"),
    )


def move_in_steps(lease: Lease, checks: list[Check]) -> list[Step]:
    """What to do before handing over the keys, from the lease checklist."""
    status = {check.key: check.status for check in checks}
    urls = {check.key: check.url for check in checks}
    documents_url = reverse("rental:lease_documents", kwargs={"pk": lease.pk})
    steps = [
        Step(
            _("Lease signed"),
            status.get("signed_lease") == OK,
            urls.get("signed_lease") or documents_url,
        ),
        Step(
            _("Entry inventory signed"),
            status.get("entry_inventory") == OK,
            reverse("rental:lease_inventories", kwargs={"pk": lease.pk}),
        ),
        Step(_("Insurance certificate"), status.get("insurance") == OK, documents_url),
        Step(
            _("Rent schedule"),
            has_schedule(lease),
            reverse("rental:lease_payments", kwargs={"pk": lease.pk}),
        ),
    ]
    if lease.deposit_amount.amount > 0:
        steps.insert(
            2, Step(_("Security deposit received"), deposit_entry(lease) is not None)
        )
    return steps
