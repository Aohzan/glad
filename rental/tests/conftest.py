"""Fixtures of the rental tests."""

import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from moneyed import Money

from base.models import Document
from base.services.documents import attach_upload
from property.models import Lease, LeaseParty, Property
from tests.conftest import (  # noqa: F401
    ADMIN_PASSWORD,
    ADMIN_USER,
    TEST_PASSWORD,
    TEST_USER,
    admin_client,
    admin_user,
    client,
    user,
    user_client,
)

TODAY = datetime.date.today()
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


@pytest.fixture
def prop():
    return Property.objects.create(
        name="Rue des Lilas",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date(2015, 1, 1),
        construction_year=2015,
        dpe_rating="C",
        dpe_date=TODAY - datetime.timedelta(days=365),
        landlord_name="SCI Lilas",
        landlord_address="1 rue des Lilas\n75000 Paris",
    )


@pytest.fixture
def lease(prop):
    lease = Lease.objects.create(
        property=prop,
        lease_type=Lease.LeaseType.EMPTY,
        status=Lease.Status.ACTIVE,
        start_date=TODAY - datetime.timedelta(days=400),
        signed_date=TODAY - datetime.timedelta(days=410),
        rent_amount=Money(Decimal(800), "EUR"),
        charges_amount=Money(Decimal(50), "EUR"),
        deposit_amount=Money(Decimal(800), "EUR"),
    )
    LeaseParty.objects.create(
        lease=lease, first_name="Jean", last_name="Dupont", email="jean@example.com"
    )
    return lease


@pytest.fixture
def attach(user):  # noqa: F811
    """Attach a PDF of *kind* to *obj*."""

    def _attach(obj, kind, valid_until=None, title=""):
        return attach_upload(
            obj,
            SimpleUploadedFile(f"{kind}.pdf", PDF),
            kind=kind,
            valid_until=valid_until,
            title=title,
            user=user,
        )

    return _attach


@pytest.fixture
def complete_lease(lease, attach):
    """A lease whose checklist is complete."""
    attach(lease, Document.Kind.LEASE)
    attach(lease, Document.Kind.INVENTORY)
    attach(lease, Document.Kind.INSURANCE, TODAY + datetime.timedelta(days=200))
    attach(
        lease.property, Document.Kind.DIAGNOSTIC, TODAY + datetime.timedelta(days=900)
    )
    return lease


@pytest.fixture
def guarantor(lease):
    return LeaseParty.objects.create(
        lease=lease,
        role=LeaseParty.Role.GUARANTOR,
        first_name="Marc",
        last_name="Dupont",
        guarantee_type=LeaseParty.GuaranteeType.JOINT,
    )


@pytest.fixture
def rent_schedule(lease):
    """Monthly rent and charges of *lease* from 5 July 2026."""
    from rental.services.payments import create_rent_schedule

    lease.start_date = datetime.date(2026, 7, 1)
    lease.payment_day = 5
    lease.save()
    return create_rent_schedule(lease)
