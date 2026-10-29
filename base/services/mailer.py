"""Emails sent from the application to third parties (tenants, applicants…).

``send_email`` records a ``SentEmail`` then delivers it in a background task,
so a slow SMTP server never blocks a page. Attachments are stored documents:
the email record keeps the exact files that were sent.
"""

import datetime
import logging
from collections.abc import Sequence

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import models, transaction
from django.dispatch import Signal
from django.tasks import task

from base.models import Document, SentEmail

logger = logging.getLogger(__name__)

#: Sent with ``email`` when the delivery of a ``SentEmail`` fails.
email_failed = Signal()


def send_email(
    *,
    to: Sequence[str],
    subject: str,
    body: str,
    attachments: Sequence[Document] = (),
    cc: Sequence[str] = (),
    reply_to: str = "",
    related: models.Model | None = None,
    kind: str = "",
    reference: str = "",
    user=None,
) -> SentEmail:
    """Record an email and enqueue its delivery; the record."""
    email = SentEmail.objects.create(
        related=related,
        kind=kind,
        reference=reference,
        to=list(to),
        cc=list(cc),
        reply_to=reply_to,
        subject=subject.replace("\n", " ").strip(),
        body=body,
        sent_by=user,
    )
    email.attachments.set(attachments)
    transaction.on_commit(lambda: deliver_email.enqueue(email.pk))
    return email


@task
def deliver_email(email_id: int) -> str:
    """Send a recorded email through the configured backend."""
    email = SentEmail.objects.prefetch_related("attachments").get(pk=email_id)
    if email.status == SentEmail.Status.SENT:
        return email.status
    message = EmailMessage(
        subject=email.subject,
        body=email.body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=email.to,
        cc=email.cc,
        reply_to=[email.reply_to] if email.reply_to else None,
    )
    try:
        for document in email.attachments.all():
            with document.file.open("rb") as handle:
                message.attach(
                    document.original_name or document.title,
                    handle.read(),
                    document.mime_type or "application/octet-stream",
                )
        message.send(fail_silently=False)
    except Exception as exc:
        logger.warning("Email %s could not be sent", email.pk, exc_info=True)
        email.status = SentEmail.Status.FAILED
        email.error = f"{type(exc).__name__}: {exc}"
        email.save(update_fields=["status", "error", "updated_at"])
        email_failed.send(sender=SentEmail, email=email)
        return email.status
    email.status = SentEmail.Status.SENT
    email.error = ""
    email.sent_at = datetime.datetime.now()
    email.save(update_fields=["status", "error", "sent_at", "updated_at"])
    return email.status


def can_send_emails() -> bool:
    """Whether an SMTP server is configured (otherwise emails go to the console)."""
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")
