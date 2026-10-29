"""Rental applications: accepting one turns it into the tenant of a lease."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from base.models import Document
from property.models import Lease, LeaseParty
from rental.models import RentalApplication


@transaction.atomic
def accept(
    application: RentalApplication, lease: Lease, *, reject_others: bool
) -> None:
    """Link *application* to *lease*: its documents and guarantor follow."""
    Document.objects.filter(
        content_type=ContentType.objects.get_for_model(RentalApplication),
        object_id=application.pk,
    ).update(content_type=ContentType.objects.get_for_model(Lease), object_id=lease.pk)
    if application.guarantor_name:
        LeaseParty.objects.create(
            lease=lease,
            role=LeaseParty.Role.GUARANTOR,
            last_name=application.guarantor_name,
            guarantee_type=application.guarantee_type or LeaseParty.GuaranteeType.OTHER,
        )
    application.status = RentalApplication.Status.ACCEPTED
    application.lease = lease
    application.save(update_fields=["status", "lease", "updated_at"])
    if reject_others:
        RentalApplication.objects.filter(
            property=application.property,
            status__in=RentalApplication.OPEN_STATUSES,
        ).update(status=RentalApplication.Status.REJECTED)


def open_applications():
    return RentalApplication.objects.filter(
        status__in=RentalApplication.OPEN_STATUSES
    ).select_related("property")
