"""Tests for the checklist of a lease."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from base.models import Document
from property.models import Lease, LeaseParty
from rental.services.compliance import (
    MISSING,
    NA,
    OK,
    WARNING,
    documents_by_lease,
    issues,
    lease_checks,
)

TODAY = datetime.date.today()


def _statuses(lease, today=TODAY):
    return {check.key: check.status for check in lease_checks(lease, today=today)}


def _check(lease, key, today=TODAY):
    return next(c for c in lease_checks(lease, today=today) if c.key == key)


@pytest.mark.django_db
def test_complete_lease(complete_lease):
    checks = lease_checks(complete_lease)
    assert {c.key: c.status for c in checks} == {
        "tenants": OK,
        "landlord": OK,
        "signed_lease": OK,
        "entry_inventory": OK,
        "deposit": OK,
        "guarantee": NA,
        "insurance": OK,
        "dpe": OK,
        "diagnostics": OK,
    }
    assert issues(checks) == []
    assert _check(complete_lease, "deposit").detail == "Legal maximum: €800.00."


@pytest.mark.django_db
def test_new_lease_without_documents(lease):
    statuses = _statuses(lease)
    for key in ("signed_lease", "entry_inventory", "insurance", "diagnostics"):
        assert statuses[key] == MISSING
    check = _check(lease, "diagnostics")
    assert check.detail == (
        "To annex to the lease: Energy performance (DPE), Natural and "
        "technological risks."
    )
    assert check.url == f"/rental/lease/{lease.pk}/documents/"


@pytest.mark.django_db
def test_upcoming_lease_is_only_warned(lease):
    lease.status = Lease.Status.UPCOMING
    lease.signed_date = None
    statuses = _statuses(lease)
    assert statuses["signed_lease"] == WARNING
    assert statuses["entry_inventory"] == WARNING
    assert statuses["insurance"] == WARNING
    assert _check(lease, "entry_inventory").detail == "To do on the move-in day."


@pytest.mark.django_db
def test_tenants(lease):
    LeaseParty.objects.create(lease=lease, first_name="Anne", last_name="Leroy")
    check = _check(lease, "tenants")
    assert check.status == WARNING
    assert "Anne Leroy" in check.detail
    LeaseParty.objects.filter(lease=lease).delete()
    assert _check(lease, "tenants").status == MISSING


@pytest.mark.django_db
def test_landlord_without_address(lease, user):
    lease.property.landlord_address = ""
    check = _check(lease, "landlord")
    assert check.status == WARNING
    assert check.url == f"/property/{lease.property.pk}/edit/"


@pytest.mark.django_db
def test_signed_lease_without_document(lease):
    check = _check(lease, "signed_lease")
    assert (check.status, check.detail) == (MISSING, "Add the signed lease.")
    lease.signed_date = None
    assert _check(lease, "signed_lease").detail == "Enter the signature date."


@pytest.mark.django_db
def test_deposit_above_the_cap(lease):
    lease.deposit_amount = Money(Decimal(1000), "EUR")
    check = _check(lease, "deposit")
    assert check.status == MISSING
    assert check.detail == "€1,000.00 exceeds the legal maximum of €800.00."
    lease.lease_type = Lease.LeaseType.COMMERCIAL
    assert _check(lease, "deposit").status == NA


@pytest.mark.django_db
def test_guarantee(lease, guarantor, attach):
    assert _check(lease, "guarantee").status == MISSING
    attach(lease, Document.Kind.GUARANTEE)
    check = _check(lease, "guarantee")
    assert (check.status, check.detail) == (OK, "Marc Dupont")


@pytest.mark.django_db
def test_insurance(lease, attach):
    document = attach(lease, Document.Kind.INSURANCE)
    assert _check(lease, "insurance").detail == (
        "Enter the end of validity of the certificate."
    )
    document.valid_until = TODAY + datetime.timedelta(days=10)
    document.save()
    assert _check(lease, "insurance").status == WARNING
    document.valid_until = TODAY - datetime.timedelta(days=1)
    document.save()
    assert _check(lease, "insurance").status == MISSING
    lease.lease_type = Lease.LeaseType.MOBILITY
    assert _check(lease, "insurance").status == WARNING


@pytest.mark.django_db
def test_dpe(lease):
    prop = lease.property
    prop.dpe_rating = ""
    assert _check(lease, "dpe").detail == "No DPE recorded."
    prop.dpe_rating = "G"
    assert _check(lease, "dpe").status == MISSING
    prop.dpe_rating = "F"
    check = _check(lease, "dpe", today=datetime.date(2026, 1, 1))
    assert check.status == WARNING
    assert "The rent cannot be increased." in check.detail
    assert "Rental ban from" in check.detail
    prop.dpe_rating = "C"
    prop.dpe_date = datetime.date(2010, 1, 1)
    assert _check(lease, "dpe").detail == "The DPE has expired."
    prop.dpe_date = datetime.date(2022, 1, 1)
    check = _check(lease, "dpe", today=datetime.date(2031, 10, 1))
    assert check.detail.startswith("Expires on")


@pytest.mark.django_db
def test_expired_diagnostic(lease, attach):
    attach(
        lease.property,
        Document.Kind.DIAGNOSTIC,
        TODAY - datetime.timedelta(days=1),
        title="Électricité",
    )
    check = _check(lease, "diagnostics")
    assert (check.status, check.detail) == (WARNING, "Expired: Électricité.")


@pytest.mark.django_db
def test_documents_by_lease_in_two_queries(lease, attach, django_assert_num_queries):
    attach(lease, Document.Kind.LEASE)
    attach(lease.property, Document.Kind.DIAGNOSTIC)
    lease = Lease.objects.select_related("property").get(pk=lease.pk)
    with django_assert_num_queries(2):
        documents = documents_by_lease([lease])[lease.pk]
    assert [d.kind for d in documents.lease] == [Document.Kind.LEASE]
    assert [d.kind for d in documents.property] == [Document.Kind.DIAGNOSTIC]


@pytest.mark.django_db
def test_entry_inventory_signed_in_the_app(lease):
    from rental.models import Inventory
    from rental.services.inventories import create_entry

    inventory = create_entry(lease, TODAY)
    assert _check(lease, "entry_inventory").status == MISSING
    inventory.status = Inventory.Status.SIGNED
    inventory.save()
    assert _check(lease, "entry_inventory").status == OK
