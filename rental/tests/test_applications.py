"""Tests for the rental applications."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from base.models import Document
from base.services.documents import documents_of
from property.models import Lease, LeaseParty
from rental.models import RentalApplication
from rental.tests.conftest import PDF


@pytest.fixture
def application(prop):
    return RentalApplication.objects.create(
        property=prop,
        first_name="Anne",
        last_name="Leroy",
        email="anne@example.com",
        monthly_income=Decimal(2400),
        rent_amount=Decimal(850),
        guarantor_name="Paul Leroy",
        guarantee_type="joint",
    )


@pytest.mark.django_db
def test_model(application):
    assert str(application) == "Anne Leroy"
    assert application.is_open
    assert application.effort_rate == Decimal("35.4")
    application.monthly_income = None
    assert application.effort_rate is None


@pytest.mark.django_db
def test_list(user_client, application):
    other = RentalApplication.objects.create(
        property=application.property,
        last_name="Martin",
        status=RentalApplication.Status.REJECTED,
    )
    response = user_client.get(reverse("rental:applications"))
    assert response.context["open"] == [application]
    assert response.context["closed"] == [other]
    assert "35.4" in response.content.decode() or "35,4" in response.content.decode()


@pytest.mark.django_db
def test_create_and_edit(user_client, prop):
    url = reverse("rental:new_application")
    assert user_client.get(url, {"property": "x"}).context["form"].initial == {}
    response = user_client.get(url, {"property": prop.pk})
    assert response.context["form"].initial["property"] == prop.pk
    response = user_client.post(url, {"property": prop.pk, "last_name": ""})
    assert response.status_code == 200
    response = user_client.post(
        url, {"property": prop.pk, "last_name": "Martin", "monthly_income": "3000"}
    )
    application = RentalApplication.objects.get()
    assert response.url == reverse("rental:application_detail", args=[application.pk])
    response = user_client.post(
        reverse("rental:edit_application", args=[application.pk]),
        {"property": prop.pk, "last_name": "Martin", "first_name": "Luc"},
    )
    application.refresh_from_db()
    assert application.name == "Luc Martin"


@pytest.mark.django_db
def test_detail_documents_and_status(user_client, application):
    url = reverse("rental:application_detail", args=[application.pk])
    response = user_client.get(url)
    content = response.content.decode()
    assert "Forbidden documents" in content
    assert reverse("rental:accept_application", args=[application.pk]) in content
    upload = reverse("rental:upload_application_document", args=[application.pk])
    response = user_client.post(
        upload, {"file": SimpleUploadedFile("cni.pdf", PDF), "kind": "identity"}
    )
    assert response.url == url
    assert documents_of(application).get().kind == Document.Kind.IDENTITY
    response = user_client.post(upload, {"kind": "lease"})
    assert response.status_code == 400
    status_url = reverse("rental:set_application_status", args=[application.pk])
    user_client.post(status_url, {"status": "reviewing"})
    application.refresh_from_db()
    assert application.status == RentalApplication.Status.REVIEWING
    user_client.post(status_url, {"status": "accepted"})
    application.refresh_from_db()
    assert application.status == RentalApplication.Status.REVIEWING


@pytest.mark.django_db
def test_accept(user_client, application, lease):
    other = RentalApplication.objects.create(
        property=application.property, last_name="B"
    )
    user_client.post(
        reverse("rental:upload_application_document", args=[application.pk]),
        {"file": SimpleUploadedFile("paie.pdf", PDF), "kind": "income"},
    )
    url = reverse("rental:accept_application", args=[application.pk])
    response = user_client.get(url)
    assert response.context["tenant_form"].initial["last_name"] == "Leroy"
    assert response.context["form"].initial["rent_amount"] == lease.rent_amount
    assert "reject_others" in response.content.decode()
    response = user_client.post(url, {"tenant-last_name": ""})
    assert response.status_code == 200
    response = user_client.post(
        url,
        {
            "tenant-first_name": "Anne",
            "tenant-last_name": "Leroy",
            "tenant-email": "anne@example.com",
            "lease_type": Lease.LeaseType.EMPTY,
            "status": Lease.Status.UPCOMING,
            "start_date": "2026-12-01",
            "rent_amount_0": "800",
            "rent_amount_1": "EUR",
            "charges_amount_0": "50",
            "charges_amount_1": "EUR",
            "deposit_amount_0": "800",
            "deposit_amount_1": "EUR",
            "periodicity": "monthly",
            "payment_day": "1",
            "charges_mode": "provision",
            "reject_others": "on",
        },
    )
    new_lease = Lease.objects.exclude(pk=lease.pk).get()
    assert response.url == reverse("rental:lease_detail", args=[new_lease.pk])
    application.refresh_from_db()
    assert (application.status, application.lease) == (
        RentalApplication.Status.ACCEPTED,
        new_lease,
    )
    other.refresh_from_db()
    assert other.status == RentalApplication.Status.REJECTED
    assert [p.name for p in new_lease.tenants] == ["Anne Leroy"]
    (guarantor,) = new_lease.guarantors
    assert (guarantor.name, guarantor.guarantee_type) == ("Paul Leroy", "joint")
    assert documents_of(new_lease).get().kind == Document.Kind.INCOME
    assert user_client.get(url).status_code == 404


@pytest.mark.django_db
def test_accept_without_previous_lease(user_client, prop):
    application = RentalApplication.objects.create(property=prop, last_name="Seul")
    response = user_client.get(
        reverse("rental:accept_application", args=[application.pk])
    )
    assert "rent_amount" not in response.context["form"].initial


@pytest.mark.django_db
def test_accept_keeps_the_other_applications(prop):
    from rental.services.applications import accept

    first = RentalApplication.objects.create(property=prop, last_name="A")
    second = RentalApplication.objects.create(property=prop, last_name="B")
    lease = Lease.objects.create(
        property=prop, start_date="2026-01-01", rent_amount=100
    )
    accept(first, lease, reject_others=False)
    second.refresh_from_db()
    assert second.is_open
    assert not LeaseParty.objects.filter(lease=lease).exists()
