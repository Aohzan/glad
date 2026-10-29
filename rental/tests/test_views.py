"""Tests for the rental views."""

import datetime

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from base.models import Document, SentEmail
from base.services.documents import documents_of
from property.models import LeaseParty, ManagementMandate
from property.services.checks import check_occurrence
from rental.models import RentReceipt
from rental.tests.conftest import PDF

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.mark.django_db
def test_dashboard(user_client, lease):
    response = user_client.get(reverse("rental:dashboard"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Rue des Lilas" in content
    assert reverse("rental:lease_detail", args=[lease.pk]) in content
    assert response.context["running_count"] == 1
    assert response.context["issue_rows"][0].lease == lease
    assert response.context["nav_section"] == "rental"


@pytest.mark.django_db
def test_dashboard_without_lease(user_client):
    response = user_client.get(reverse("rental:dashboard"))
    assert "No lease to manage." in response.content.decode()


@pytest.mark.django_db
def test_dashboard_lists_the_leases_under_mandate(user_client, lease):
    ManagementMandate.objects.create(
        property=lease.property,
        manager_name="Foncia",
        start_date=datetime.date(2020, 1, 1),
    )
    response = user_client.get(reverse("rental:dashboard"))
    assert response.context["self_managed"] == []
    assert "Foncia" in response.content.decode()


@pytest.mark.django_db
def test_lease_detail(user_client, lease, guarantor):
    response = user_client.get(reverse("rental:lease_detail", args=[lease.pk]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Jean Dupont" in content
    assert "Marc Dupont" in content
    assert "SCI Lilas" in content
    assert "3 months (legal duration)" not in content
    assert "36 months (legal duration)" in content
    assert response.context["issue_count"] > 0


@pytest.mark.django_db
def test_lease_detail_under_mandate(user_client, lease):
    ManagementMandate.objects.create(
        property=lease.property,
        manager_name="Foncia",
        start_date=datetime.date(2020, 1, 1),
    )
    response = user_client.get(reverse("rental:lease_detail", args=[lease.pk]))
    content = response.content.decode()
    assert "Managed by Foncia" in content
    assert 'id="lease-checklist"' not in content
    assert response.context["checks"] == []
    assert not response.context["show_steps"]


@pytest.mark.django_db
def test_lease_documents(user_client, complete_lease):
    response = user_client.get(
        reverse("rental:lease_documents", args=[complete_lease.pk])
    )
    assert response.status_code == 200
    assert len(response.context["lease_documents"]) == 3
    assert len(response.context["property_documents"]) == 1


@pytest.mark.django_db
def test_upload_a_lease_document(user_client, lease):
    response = user_client.post(
        reverse("rental:upload_lease_document", args=[lease.pk]),
        {
            "file": SimpleUploadedFile("assurance.pdf", PDF),
            "kind": Document.Kind.INSURANCE,
            "valid_until": "2030-01-01",
        },
    )
    assert response.status_code == 302
    (document,) = documents_of(lease)
    assert document.kind == Document.Kind.INSURANCE
    assert document.title == "assurance"
    assert document.valid_until == datetime.date(2030, 1, 1)


@pytest.mark.django_db
def test_a_diagnostic_goes_to_the_property(user_client, lease):
    user_client.post(
        reverse("rental:upload_lease_document", args=[lease.pk]),
        {
            "file": SimpleUploadedFile("dpe.pdf", PDF),
            "kind": Document.Kind.DIAGNOSTIC,
            "title": "DPE",
        },
    )
    assert not documents_of(lease).exists()
    assert documents_of(lease.property).get().title == "DPE"


@pytest.mark.django_db
def test_upload_refuses_another_file_type(user_client, lease):
    response = user_client.post(
        reverse("rental:upload_lease_document", args=[lease.pk]),
        {
            "file": SimpleUploadedFile("page.pdf", b"<html>"),
            "kind": Document.Kind.LEASE,
        },
    )
    assert response.status_code == 400
    assert response.context["form"].errors["file"]
    assert not documents_of(lease).exists()


@pytest.mark.django_db
def test_upload_needs_a_file(user_client, lease):
    response = user_client.post(
        reverse("rental:upload_lease_document", args=[lease.pk]),
        {"kind": Document.Kind.LEASE},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_add_a_guarantor(user_client, lease):
    url = reverse("rental:new_party", args=[lease.pk])
    response = user_client.get(url, {"role": "guarantor"})
    assert response.context["form"].initial["role"] == "guarantor"
    response = user_client.post(
        url,
        {"role": "guarantor", "first_name": "Marc", "last_name": "Dupont"},
    )
    assert response.status_code == 200
    assert response.context["form"].errors["guarantee_type"]
    response = user_client.post(
        url,
        {
            "role": "guarantor",
            "first_name": "Marc",
            "last_name": "Dupont",
            "guarantee_type": "visale",
            "birth_date": "1960-05-01",
        },
    )
    assert response.status_code == 302
    (guarantor,) = lease.guarantors
    assert guarantor.guarantee_type == LeaseParty.GuaranteeType.VISALE


@pytest.mark.django_db
def test_edit_a_tenant_drops_the_guarantee_type(user_client, lease):
    tenant = lease.tenants[0]
    url = reverse("rental:edit_party", args=[lease.pk, tenant.pk])
    assert user_client.get(url, {"role": "nope"}).context["form"].initial == {
        "role": "tenant",
        "first_name": "Jean",
        "last_name": "Dupont",
        "email": "jean@example.com",
        "phone": "",
        "birth_date": None,
        "birth_place": "",
        "address": "",
        "guarantee_type": "",
    }
    response = user_client.post(
        url,
        {
            "role": "tenant",
            "first_name": "Jean",
            "last_name": "Durand",
            "email": "jean@example.com",
            "guarantee_type": "joint",
        },
    )
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert (tenant.last_name, tenant.guarantee_type) == ("Durand", "")


@pytest.mark.django_db
def test_edit_a_party_of_another_lease(user_client, lease, prop):
    other = lease.__class__.objects.create(
        property=prop, start_date=lease.start_date, rent_amount=lease.rent_amount
    )
    tenant = lease.tenants[0]
    response = user_client.get(reverse("rental:edit_party", args=[other.pk, tenant.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_a_party(user_client, lease, guarantor):
    url = reverse("rental:delete_party", args=[lease.pk, guarantor.pk])
    assert user_client.get(url).status_code == 405
    response = user_client.post(url)
    assert response.status_code == 302
    assert lease.guarantors == []


@pytest.mark.django_db
def test_views_need_a_login(client, lease):
    response = client.get(reverse("rental:lease_detail", args=[lease.pk]))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# ── Payments and emails ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_payments_without_schedule(user_client, lease):
    url = reverse("rental:lease_payments", args=[lease.pk])
    response = user_client.get(url)
    assert response.status_code == 200
    assert not response.context["has_schedule"]
    assert "No rent recorded for this lease yet." in response.content.decode()
    assert (
        user_client.get(reverse("rental:create_schedule", args=[lease.pk])).status_code
        == 405
    )
    response = user_client.post(reverse("rental:create_schedule", args=[lease.pk]))
    assert response.status_code == 302
    response = user_client.get(url)
    assert response.context["has_schedule"]
    assert response.context["rows"]
    user_client.post(reverse("rental:create_schedule", args=[lease.pk]))
    assert lease.ledger_entries.count() == 2


@pytest.mark.django_db
def test_payments_grid(user_client, lease, rent_schedule):
    rent, charges = rent_schedule
    for entry in (rent, charges):
        check_occurrence(entry, datetime.date(2026, 7, 5))
    response = user_client.get(reverse("rental:lease_payments", args=[lease.pk]))
    content = response.content.decode()
    assert response.context["arrears"] > 0
    assert reverse("rental:download_receipt", args=[lease.pk, "2026-07"]) in content
    assert f"?property={lease.property.pk}" in content
    assert "Send a reminder" in content


@pytest.mark.django_db
def test_download_receipt(user_client, lease, rent_schedule):
    rent, _charges = rent_schedule
    check_occurrence(rent, datetime.date(2026, 7, 5))
    response = user_client.get(
        reverse("rental:download_receipt", args=[lease.pk, "2026-07"])
    )
    assert response["Content-Type"] == "application/pdf"
    assert 'filename="recu-2026-07.pdf"' in response["Content-Disposition"]
    assert response.content.startswith(b"%PDF")
    assert (
        user_client.get(
            reverse("rental:download_receipt", args=[lease.pk, "2026-08"])
        ).status_code
        == 404
    )
    assert (
        user_client.get(
            reverse("rental:download_receipt", args=[lease.pk, "1999-01"])
        ).status_code
        == 404
    )


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_compose_and_send_a_receipt(
    user_client, user, lease, rent_schedule, django_capture_on_commit_callbacks
):
    for entry in rent_schedule:
        check_occurrence(entry, datetime.date(2026, 7, 5))
    url = reverse("rental:compose_email", args=[lease.pk, "receipt"])
    response = user_client.get(url, {"period": "2026-07"})
    assert response.status_code == 200
    form = response.context["form"]
    assert form.initial["to"] == "jean@example.com"
    assert form.initial["subject"] == "Quittance de loyer — juillet 2026"
    assert response.context["attachment"] == "quittance-2026-07.pdf"
    with django_capture_on_commit_callbacks(execute=True):
        response = user_client.post(
            url,
            {
                "period": "2026-07",
                "to": "jean@example.com; anne@example.com",
                "cc": "",
                "subject": "Votre quittance",
                "body": "Bonjour,",
            },
        )
    assert response.status_code == 302
    (message,) = mail.outbox
    assert message.to == ["jean@example.com", "anne@example.com"]
    assert message.reply_to == ["user@site.com"]
    assert message.attachments[0].filename == "quittance-2026-07.pdf"
    receipt = RentReceipt.objects.get()
    assert receipt.sent_at is not None
    response = user_client.get(reverse("rental:lease_emails", args=[lease.pk]))
    content = response.content.decode()
    assert "Votre quittance" in content
    assert "quittance-2026-07.pdf" in content


@pytest.mark.django_db
def test_compose_validates_the_addresses(user_client, lease):
    url = reverse("rental:compose_email", args=[lease.pk, "insurance_request"])
    response = user_client.get(url)
    assert response.context["attachment"] is None
    response = user_client.post(
        url, {"to": "jean@example.com, nope", "subject": "S", "body": "B"}
    )
    assert response.status_code == 200
    assert response.context["form"].errors["to"]
    response = user_client.post(url, {"to": "", "subject": "S", "body": "B"})
    assert response.context["form"].errors["to"]
    assert not SentEmail.objects.exists()


@pytest.mark.django_db
def test_compose_unknown_kind_or_period(user_client, lease, rent_schedule):
    assert (
        user_client.get(
            reverse("rental:compose_email", args=[lease.pk, "nope"])
        ).status_code
        == 404
    )
    url = reverse("rental:compose_email", args=[lease.pk, "rent_call"])
    assert user_client.get(url).status_code == 404
    assert user_client.get(url, {"period": "2026-08"}).status_code == 200
    url = reverse("rental:compose_email", args=[lease.pk, "receipt"])
    assert user_client.get(url, {"period": "2026-08"}).status_code == 404


@pytest.mark.django_db
def test_formal_notice_copies_the_guarantors(user_client, lease, guarantor):
    guarantor.email = "marc@example.com"
    guarantor.save()
    response = user_client.get(
        reverse("rental:compose_email", args=[lease.pk, "formal_notice"])
    )
    assert response.context["form"].initial["cc"] == "marc@example.com"
    assert "registered letter" in response.content.decode()


@pytest.mark.django_db
def test_emails_tab(user_client, lease):
    response = user_client.get(reverse("rental:lease_emails", args=[lease.pk]))
    assert response.status_code == 200
    assert "No email sent yet." in response.content.decode()
    assert [kind.key for kind in response.context["kinds"]] == [
        "reminder",
        "formal_notice",
        "rent_revision",
        "insurance_request",
    ]


@pytest.mark.django_db
def test_dashboard_payments(user_client, lease, rent_schedule):
    response = user_client.get(reverse("rental:dashboard"))
    payments = response.context["payments"]
    assert payments["arrears"] > 0
    assert set(payments) == {"expected", "received", "arrears"}
