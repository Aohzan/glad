"""Tests for the electronic signature of the leases and inventories."""

import datetime

import pytest

from base.models import Document
from base.services.documents import documents_of
from base.services.pdf import BasePdf
from notifications.models import Notification
from rental.models import Inventory, SignatureRequest
from rental.services import signature
from rental.services.documenso import Documenso, DocumensoError
from rental.services.inventories import create_entry


class FakeClient(Documenso):
    """Documenso answering from memory."""

    def __init__(self, envelope=None, error=None):
        self.sent = []
        self.envelope_data = envelope or {}
        self.error = error

    def send(self, **kwargs):
        if self.error:
            raise self.error
        self.sent.append(kwargs)
        return "envelope_1"

    def envelope(self, envelope_id):
        if self.error:
            raise self.error
        return self.envelope_data

    def download_signed(self, envelope):
        return b"%PDF-signed"


def test_signature_page_and_page_count():
    pdf = BasePdf()
    pdf.add_page()
    signature.add_signature_page(
        pdf, [("Bailleur", "SCI"), ("Locataire", "Jean")], "Paris"
    )
    content = pdf.render()
    assert signature.page_count(content) == 2


@pytest.mark.django_db
def test_signers(lease, guarantor):
    assert signature.signers_of(lease, "owner@example.com") == [
        ("Bailleur", "SCI Lilas", "owner@example.com"),
        ("Locataire", "Jean Dupont", "jean@example.com"),
    ]
    with pytest.raises(signature.SignatureError, match="your settings"):
        signature.signers_of(lease, "")
    lease.parties.create(last_name="Sans email")
    with pytest.raises(signature.SignatureError, match="Sans email"):
        signature.signers_of(lease, "owner@example.com")


@pytest.mark.django_db
def test_signers_limits(lease):
    lease.parties.all().delete()
    with pytest.raises(signature.SignatureError, match="no tenant"):
        signature.signers_of(lease, "owner@example.com")
    for index in range(5):
        lease.parties.create(last_name=f"T{index}", email=f"t{index}@example.com")
    with pytest.raises(signature.SignatureError, match="At most 5"):
        signature.signers_of(lease, "owner@example.com")


def _request(lease, client=None):
    return signature.request_signature(
        lease,
        title="Bail — Rue des Lilas",
        pdf=b"%PDF /Type /Page /Type /Pages /Type /Page",
        signers=[
            ("Bailleur", "SCI", "o@example.com"),
            ("Locataire", "Jean", "j@example.com"),
        ],
        client=client or FakeClient(),
    )


@pytest.mark.django_db
def test_request_signature(lease):
    client = FakeClient()
    request = _request(lease, client)
    assert request.external_id == "envelope_1"
    assert request.target == lease
    assert [s["email"] for s in request.signers] == ["o@example.com", "j@example.com"]
    (sent,) = client.sent
    signers = sent["signers"]
    assert signers[1].fields[0].page == 2
    assert signers[1].fields[0].y == signature._TOP + signature._STEP
    assert sent["external_id"] == f"glad-lease-{lease.pk}"
    (original,) = documents_of(request)
    assert original.original_name == "Bail — Rue des Lilas.pdf"


@pytest.mark.django_db
def test_request_signature_error(lease):
    with pytest.raises(DocumensoError):
        _request(lease, FakeClient(error=DocumensoError("down")))
    assert not SignatureRequest.objects.exists()


@pytest.mark.django_db
def test_refresh_pending_then_completed(lease, user):
    lease.signed_date = None
    lease.save()
    request = _request(lease)
    recipients = [
        {
            "name": "SCI",
            "email": "o@example.com",
            "signingStatus": "SIGNED",
            "signedAt": "2026-10-01",
        },
        {"name": "Jean", "email": "j@example.com", "signingStatus": "NOT_SIGNED"},
    ]
    signature.refresh(
        request, FakeClient({"status": "PENDING", "recipients": recipients})
    )
    request.refresh_from_db()
    assert request.status == SignatureRequest.Status.PENDING
    assert [s["status"] for s in request.signers] == ["signed", "not_signed"]
    recipients[1]["signingStatus"] = "SIGNED"
    signature.refresh(
        request, FakeClient({"status": "COMPLETED", "recipients": recipients})
    )
    request.refresh_from_db()
    assert request.status == SignatureRequest.Status.COMPLETED
    assert request.completed_at is not None
    signed = request.signed_document
    assert signed is not None
    assert (signed.kind, signed.content_object) == (Document.Kind.LEASE, lease)
    lease.refresh_from_db()
    assert lease.signed_date == datetime.date.today()
    assert Notification.objects.filter(type_key="signature_completed").exists()


@pytest.mark.django_db
def test_completed_inventory(lease):
    inventory = create_entry(lease, datetime.date.today())
    request = signature.request_signature(
        inventory,
        title="État des lieux",
        pdf=b"%PDF",
        signers=[("Bailleur", "SCI", "o@example.com")],
        client=FakeClient(),
    )
    signature.refresh(request, FakeClient({"status": "COMPLETED", "recipients": []}))
    inventory.refresh_from_db()
    assert inventory.status == Inventory.Status.SIGNED
    request.refresh_from_db()
    assert request.signed_document.kind == Document.Kind.INVENTORY
    assert signature.lease_of(inventory) == lease


@pytest.mark.django_db
def test_rejected(lease):
    request = _request(lease)
    signature.refresh(request, FakeClient({"status": "REJECTED", "recipients": []}))
    request.refresh_from_db()
    assert request.status == SignatureRequest.Status.REJECTED


@pytest.mark.django_db
def test_poll_signatures(lease, monkeypatch):
    assert not signature.has_pending()
    assert signature.poll_signatures() == "0 request(s) checked, 0 finished, 0 failed"
    _request(lease)
    assert signature.has_pending()
    monkeypatch.setattr(
        signature,
        "Documenso",
        lambda: FakeClient({"status": "COMPLETED", "recipients": []}),
    )
    assert signature.poll_signatures() == "1 request(s) checked, 1 finished, 0 failed"
    assert not signature.has_pending()


@pytest.mark.django_db
def test_poll_signatures_failure(lease, monkeypatch):
    request = _request(lease)
    monkeypatch.setattr(
        signature, "Documenso", lambda: FakeClient(error=DocumensoError("down"))
    )
    with pytest.raises(DocumensoError, match="No signature request could be checked"):
        signature.poll_signatures()
    request.refresh_from_db()
    assert request.error == "down"


def test_poll_job_is_registered():
    from base.scheduler import get_job

    job = get_job("poll_signatures")
    assert job.every == datetime.timedelta(minutes=15)
    assert job.when == "rental.services.signature.has_pending"
