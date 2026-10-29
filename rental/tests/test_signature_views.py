"""Tests for the views of the lease PDF and of the signatures."""

import datetime

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from rental.models import SignatureRequest
from rental.services import signature
from rental.services.documenso import DocumensoError
from rental.services.inventories import create_entry
from rental.tests.test_signature import FakeClient


def _messages(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.fixture
def documenso(settings, monkeypatch):
    settings.DOCUMENSO_URL = "https://sign.example.com"
    settings.DOCUMENSO_API_TOKEN = "token"
    client = FakeClient({"status": "PENDING", "recipients": []})
    monkeypatch.setattr(signature, "Documenso", lambda: client)
    return client


@pytest.mark.django_db
def test_lease_pdf(user_client, lease):
    response = user_client.get(reverse("rental:lease_pdf", args=[lease.pk]))
    assert response["Content-Type"] == "application/pdf"
    assert f'filename="bail-{lease.pk}.pdf"' in response["Content-Disposition"]


@pytest.mark.django_db
def test_sign_without_documenso(user_client, lease, settings):
    settings.DOCUMENSO_URL = ""
    response = user_client.get(reverse("rental:lease_detail", args=[lease.pk]))
    assert not response.context["can_sign"]
    assert "DOCUMENSO_URL" in response.content.decode()
    response = user_client.post(reverse("rental:sign_lease", args=[lease.pk]))
    assert "No signature service is configured." in _messages(response)


@pytest.mark.django_db
def test_sign_lease(user_client, lease, documenso):
    response = user_client.post(reverse("rental:sign_lease", args=[lease.pk]))
    assert "Sent for signature to 2 people." in _messages(response)
    request = SignatureRequest.objects.get()
    assert request.title == "Bail — Rue des Lilas"
    response = user_client.get(reverse("rental:lease_detail", args=[lease.pk]))
    assert response.context["signatures"].get() == request
    assert "Check now" in response.content.decode()
    response = user_client.get(reverse("rental:dashboard"))
    assert list(response.context["pending_signatures"]) == [request]
    user_client.post(reverse("rental:refresh_signature", args=[request.pk]))
    documenso.error = DocumensoError("down")
    response = user_client.post(reverse("rental:refresh_signature", args=[request.pk]))
    assert "down" in _messages(response)


@pytest.mark.django_db
def test_sign_errors(user_client, lease, documenso):
    lease.parties.update(email="")
    response = user_client.post(reverse("rental:sign_lease", args=[lease.pk]))
    assert "No email address for Jean Dupont." in _messages(response)
    assert not SignatureRequest.objects.exists()


@pytest.mark.django_db
def test_sign_inventory(user_client, lease, documenso):
    inventory = create_entry(lease, datetime.date.today())
    response = user_client.get(reverse("rental:inventory_detail", args=[inventory.pk]))
    assert response.context["can_sign"]
    response = user_client.post(reverse("rental:sign_inventory", args=[inventory.pk]))
    assert response.url == reverse("rental:inventory_detail", args=[inventory.pk])
    request = SignatureRequest.objects.get()
    assert request.title == "État des lieux d'entrée — Rue des Lilas"
    response = user_client.get(reverse("rental:lease_detail", args=[lease.pk]))
    assert response.context["signatures"].get() == request


@pytest.mark.django_db
def test_signature_pending_notification(lease, documenso):
    from rental import notifications

    request = signature.request_signature(
        lease,
        title="Bail",
        pdf=b"%PDF",
        signers=[
            ("Bailleur", "SCI", "o@example.com"),
            ("Locataire", "Jean", "j@example.com"),
        ],
        client=documenso,
    )
    today = datetime.date.today()
    assert list(notifications._signature_pending({"days": 7}, today)) == []
    (event,) = notifications._signature_pending(
        {"days": 7}, today + datetime.timedelta(days=8)
    )
    assert event.key == str(request.pk)
    assert event.body == "Waiting for SCI, Jean."


@pytest.mark.django_db
def test_refresh_a_finished_request(user_client, lease, documenso):
    request = signature.request_signature(
        lease, title="Bail", pdf=b"%PDF", signers=[], client=documenso
    )
    request.status = SignatureRequest.Status.COMPLETED
    request.save()
    assert str(request) == "Bail"
    response = user_client.post(reverse("rental:refresh_signature", args=[request.pk]))
    assert response.url == reverse("rental:lease_detail", args=[lease.pk])
