"""Tests for the stored documents (validation, storage, download, deletion)."""

import os

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from base.models import Document
from base.services.documents import (
    attach_pdf,
    attach_upload,
    documents_of,
    sniff_mime_type,
    validate_upload,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (PDF, "application/pdf"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 12, "image/jpeg"),
        (PNG, "image/png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00", "image/heic"),
        (b"<html><script>", None),
        (b"", None),
    ],
)
def test_sniff_mime_type(head, expected):
    assert sniff_mime_type(head) == expected


def test_validate_upload_accepts_a_pdf():
    assert validate_upload(SimpleUploadedFile("lease.PDF", PDF)) == "application/pdf"


def test_validate_upload_rejects_a_disguised_file():
    with pytest.raises(ValidationError):
        validate_upload(SimpleUploadedFile("lease.pdf", b"<html><script>alert(1)"))


def test_validate_upload_rejects_a_mismatched_extension():
    with pytest.raises(ValidationError):
        validate_upload(SimpleUploadedFile("photo.html", PNG))


def test_validate_upload_rejects_a_large_file(settings):
    settings.DOCUMENT_MAX_SIZE = 10
    with pytest.raises(ValidationError, match="too large"):
        validate_upload(SimpleUploadedFile("lease.pdf", PDF))


@pytest.mark.django_db
def test_attach_upload_stores_the_file_under_a_random_name(user):
    document = attach_upload(
        user,
        SimpleUploadedFile("../../Bail signé.pdf", PDF),
        kind=Document.Kind.LEASE,
        user=user,
    )
    assert document.title == "Bail signé"
    assert document.original_name == "Bail signé.pdf"
    assert document.mime_type == "application/pdf"
    assert document.size == len(PDF)
    assert document.uploaded_by == user
    stored_name = document.file.name or ""
    assert stored_name.startswith("documents/")
    assert "Bail" not in stored_name
    assert not document.is_image
    assert not document.is_expired
    assert list(documents_of(user)) == [document]
    assert str(document) == "Bail signé"


@pytest.mark.django_db
def test_attach_pdf_stores_generated_content(user):
    document = attach_pdf(
        user,
        PDF,
        filename="quittance-2026-10.pdf",
        title="Quittance octobre 2026",
        kind=Document.Kind.RECEIPT,
    )
    with document.file.open("rb") as handle:
        assert handle.read() == PDF
    assert document.kind == Document.Kind.RECEIPT


@pytest.mark.django_db
def test_document_expiry(user):
    import datetime

    document = attach_upload(
        user,
        SimpleUploadedFile("attestation.png", PNG),
        valid_until=datetime.date(2000, 1, 1),
    )
    assert document.is_expired
    assert document.is_image


@pytest.mark.django_db
def test_download_a_pdf_as_attachment(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    response = user_client.get(reverse("download_document", args=[document.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment")
    assert response["Cache-Control"] == "private, no-store"
    assert b"".join(response.streaming_content) == PDF


@pytest.mark.django_db
def test_download_an_image_inline(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("photo.png", PNG))
    response = user_client.get(reverse("download_document", args=[document.pk]))
    assert response["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
def test_download_a_missing_file(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    os.remove(document.file.path)
    response = user_client.get(reverse("download_document", args=[document.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_download_requires_a_login(client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    response = client.get(reverse("download_document", args=[document.pk]))
    assert response.status_code == 302


@pytest.mark.django_db
def test_delete_document_removes_the_file(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    path = document.file.path
    response = user_client.post(
        reverse("delete_document", args=[document.pk]), {"next": "/property/"}
    )
    assert response.status_code == 302
    assert response.url == "/property/"
    assert not Document.objects.filter(pk=document.pk).exists()
    assert not os.path.exists(path)


@pytest.mark.django_db
def test_delete_document_ignores_an_external_next(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    response = user_client.post(
        reverse("delete_document", args=[document.pk]),
        {"next": "https://evil.example/"},
    )
    assert response.url == reverse("index")


@pytest.mark.django_db
def test_delete_document_requires_post(user_client, user):
    document = attach_upload(user, SimpleUploadedFile("bail.pdf", PDF))
    response = user_client.get(reverse("delete_document", args=[document.pk]))
    assert response.status_code == 405
