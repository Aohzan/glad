"""Sending of the emails of a lease, with the receipt PDF when needed."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from base.models import Document, SentEmail
from base.services.documents import attach_pdf
from base.services.mailer import send_email
from property.models import Lease
from rental.emails import RECEIPT, EmailKind
from rental.models import ChargesReconciliation, DepositSettlement
from rental.services.charges import statement_pdf
from rental.services.departure import statement_pdf as deposit_statement_pdf
from rental.services.payments import Period
from rental.services.receipts import receipt_for, store_receipt_pdf


def send_lease_email(
    lease: Lease,
    kind: EmailKind,
    *,
    to: list[str],
    cc: list[str],
    subject: str,
    body: str,
    period: Period | None = None,
    reconciliation: ChargesReconciliation | None = None,
    settlement: DepositSettlement | None = None,
    user=None,
) -> SentEmail:
    """Record and enqueue an email to the tenants of *lease*."""
    with transaction.atomic():
        attachments = []
        receipt = None
        if kind.key == RECEIPT and period is not None:
            receipt = receipt_for(lease, period)
            attachments.append(store_receipt_pdf(receipt, user))
        if reconciliation is not None:
            attachments.append(
                attach_pdf(
                    lease,
                    statement_pdf(reconciliation),
                    filename=f"regularisation-charges-{reconciliation.period_end:%Y}.pdf",
                    title=f"Régularisation des charges {reconciliation.period_end:%Y}",
                    kind=Document.Kind.STATEMENT,
                    user=user,
                )
            )
        if settlement is not None:
            attachments.append(
                attach_pdf(
                    lease,
                    deposit_statement_pdf(settlement),
                    filename="restitution-depot-de-garantie.pdf",
                    title="Restitution du dépôt de garantie",
                    kind=Document.Kind.STATEMENT,
                    user=user,
                )
            )
        email = send_email(
            to=to,
            cc=cc,
            subject=subject,
            body=body,
            attachments=attachments,
            reply_to=getattr(user, "email", "") or "",
            related=lease,
            kind=kind.key,
            reference=(
                period.key
                if period
                else f"charges-{reconciliation.pk}"
                if reconciliation
                else ""
            ),
            user=user,
        )
        if receipt is not None:
            receipt.sent_at = timezone.now()
            receipt.save(update_fields=["sent_at", "updated_at"])
        if reconciliation is not None:
            reconciliation.status = ChargesReconciliation.Status.SENT
            reconciliation.sent_at = timezone.now()
            reconciliation.save(update_fields=["status", "sent_at", "updated_at"])
        if settlement is not None:
            settlement.sent_at = timezone.now()
            settlement.save(update_fields=["sent_at", "updated_at"])
    return email


def emails_of(lease: Lease):
    """Emails sent about *lease*, newest first."""
    return SentEmail.objects.filter(
        content_type=ContentType.objects.get_for_model(Lease), object_id=lease.pk
    ).prefetch_related("attachments")


def already_sent(lease: Lease, kind: str, reference: str) -> bool:
    return (
        emails_of(lease)
        .filter(kind=kind, reference=reference)
        .exclude(status=SentEmail.Status.FAILED)
        .exists()
    )
