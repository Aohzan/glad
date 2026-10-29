"""Tests for the emails sent from the application."""

from unittest.mock import patch

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from base.models import SentEmail
from base.services.documents import attach_upload
from base.services.mailer import (
    can_send_emails,
    deliver_email,
    email_failed,
    send_email,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="Glad <glad@example.com>")
def test_send_email_records_and_delivers(user, django_capture_on_commit_callbacks):
    document = attach_upload(user, SimpleUploadedFile("quittance.pdf", PDF))
    with django_capture_on_commit_callbacks(execute=True):
        email = send_email(
            to=["tenant@example.com"],
            cc=["guarantor@example.com"],
            subject="Quittance\nde loyer",
            body="Bonjour,",
            attachments=[document],
            reply_to="owner@example.com",
            related=user,
            kind="rent_receipt",
            reference="2026-10",
            user=user,
        )
    email.refresh_from_db()
    assert email.status == SentEmail.Status.SENT
    assert email.sent_at is not None
    assert email.subject == "Quittance de loyer"
    assert email.related == user
    assert email.reference == "2026-10"
    assert str(email) == "Quittance de loyer"
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["tenant@example.com"]
    assert message.cc == ["guarantor@example.com"]
    assert message.reply_to == ["owner@example.com"]
    assert message.from_email == "Glad <glad@example.com>"
    assert message.attachments[0].filename == "quittance.pdf"
    assert message.attachments[0].content == PDF


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_failed_delivery_is_recorded_and_signalled(
    user, django_capture_on_commit_callbacks
):
    received = []

    def handler(sender, email, **kwargs):
        received.append(email.pk)

    email_failed.connect(handler)
    try:
        with (
            patch(
                "base.services.mailer.EmailMessage.send",
                side_effect=OSError("refused"),
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            email = send_email(to=["tenant@example.com"], subject="S", body="B")
    finally:
        email_failed.disconnect(handler)
    email.refresh_from_db()
    assert email.status == SentEmail.Status.FAILED
    assert email.error == "OSError: refused"
    assert received == [email.pk]


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_sent_email_is_not_sent_again(user):
    email = SentEmail.objects.create(
        to=["tenant@example.com"], subject="S", body="B", status=SentEmail.Status.SENT
    )
    deliver_email.call(email.pk)
    assert mail.outbox == []


def test_can_send_emails(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    assert not can_send_emails()
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    assert can_send_emails()
