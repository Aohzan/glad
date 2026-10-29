"""Tests for the rental notification types."""

import datetime

import pytest
from django.urls import reverse

from base.models import Document
from property.models import Lease, ManagementMandate
from property.services.checks import check_occurrence
from rental import notifications

TODAY = datetime.date.today()
PARAMS = {"days_before": 30}


@pytest.mark.django_db
def test_compliance_issue(lease):
    (event,) = notifications._compliance_issues({}, TODAY)
    assert event.title == "Rue des Lilas — Jean Dupont: 4 items missing"
    assert event.key == f"{lease.pk}:diagnostics,entry_inventory,insurance,signed_lease"
    assert "Signed lease: Add the signed lease." in event.body
    assert event.url == reverse("rental:lease_detail", args=[lease.pk])


@pytest.mark.django_db
def test_no_compliance_issue(complete_lease):
    assert list(notifications._compliance_issues({}, TODAY)) == []


@pytest.mark.django_db
def test_leases_under_mandate_are_not_checked(lease):
    ManagementMandate.objects.create(
        property=lease.property, manager_name="Foncia", start_date=lease.start_date
    )
    assert list(notifications._compliance_issues({}, TODAY)) == []


@pytest.mark.django_db
def test_tenant_insurance(lease, attach):
    assert list(notifications._tenant_insurance(PARAMS, TODAY)) == []
    document = attach(lease, Document.Kind.INSURANCE, TODAY + datetime.timedelta(60))
    assert list(notifications._tenant_insurance(PARAMS, TODAY)) == []
    document.valid_until = TODAY + datetime.timedelta(days=20)
    document.save()
    (event,) = notifications._tenant_insurance(PARAMS, TODAY)
    assert event.title == "Tenant insurance expires soon: Rue des Lilas — Jean Dupont"
    document.valid_until = TODAY - datetime.timedelta(days=2)
    document.save()
    (event,) = notifications._tenant_insurance(PARAMS, TODAY)
    assert event.title.startswith("Tenant insurance expired")
    assert event.url == reverse("rental:lease_documents", args=[lease.pk])


@pytest.mark.django_db
def test_tenant_insurance_skips_upcoming_and_mobility_leases(lease, attach):
    attach(lease, Document.Kind.INSURANCE, TODAY)
    lease.status = Lease.Status.UPCOMING
    lease.save()
    assert list(notifications._tenant_insurance(PARAMS, TODAY)) == []
    lease.status = Lease.Status.ACTIVE
    lease.lease_type = Lease.LeaseType.MOBILITY
    lease.save()
    assert list(notifications._tenant_insurance(PARAMS, TODAY)) == []


@pytest.mark.django_db
def test_diagnostic_expiry(lease, attach):
    attach(lease.property, Document.Kind.DIAGNOSTIC, TODAY + datetime.timedelta(90))
    document = attach(
        lease.property,
        Document.Kind.DIAGNOSTIC,
        TODAY + datetime.timedelta(10),
        title="Gaz",
    )
    (event,) = notifications._diagnostic_expiry({"days_before": 60}, TODAY)
    assert event.title == "Diagnostic to renew: Gaz — Rue des Lilas"
    assert event.key.startswith(f"{document.pk}:")


def test_types_are_registered():
    from notifications.registry import get_type

    assert get_type("compliance_issue").renotify_days == 30
    assert get_type("tenant_insurance").group == "rental"
    assert get_type("diagnostic_expiry").default_params() == {"days_before": 60}


@pytest.mark.django_db
def test_rent_late(lease, rent_schedule):
    rent, charges = rent_schedule
    for month in (7, 8, 9):
        for entry in (rent, charges):
            check_occurrence(entry, datetime.date(2026, month, 5))
    today = datetime.date(2026, 10, 9)
    assert list(notifications._rent_late({"days": 5}, today)) == []
    (event,) = notifications._rent_late({"days": 4}, today)
    assert event.key == f"{lease.pk}:2026-10"
    assert event.title == "Rent of 2026-10 not received: Rue des Lilas — Jean Dupont"
    assert event.body.startswith("850,00 € still due. On ")
    assert event.url == reverse("rental:lease_payments", args=[lease.pk])
    lease.status = Lease.Status.UPCOMING
    lease.save()
    assert list(notifications._rent_late({"days": 4}, today)) == []
