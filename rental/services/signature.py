"""Electronic signature of the leases and inventories.

The PDF ends with a signature page laid out by ``add_signature_page``: the
signature and date fields of each signer are placed on it at the same
positions in the signature request. Signing is followed by polling the
provider; once everyone signed, the signed PDF is stored on the lease.
"""

import datetime
import re

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from base.models import Document
from base.services.documents import attach_pdf
from base.services.pdf import FONT, BasePdf
from notifications.registry import Event
from notifications.services import notify
from property.models import Lease
from rental.models import Inventory, SignatureRequest
from rental.services.documenso import Documenso, DocumensoError, Field, Signer
from rental.services.landlord import landlord_of

#: Signers fitting on the signature page.
MAX_SIGNERS = 5
#: Vertical position of the first signer and space between two, in % of the page.
_TOP = 22
_STEP = 15
_PAGE_MM = (210, 297)

_PAGE_RE = re.compile(rb"/Type\s*/Page\b")


class SignatureError(Exception):
    """The document cannot be sent for signature."""


def _fields(index: int, page: int) -> tuple[Field, ...]:
    y = _TOP + index * _STEP
    return (
        Field("SIGNATURE", page, 10, y, 45, 9),
        Field("DATE", page, 62, y + 2, 28, 4),
    )


def add_signature_page(pdf: BasePdf, names: list[tuple[str, str]], place: str) -> None:
    """A last page with a box per signer: (role, name) pairs, in signing order."""
    pdf.add_page()
    pdf.heading("Signatures")
    pdf.paragraph(
        f"Fait à {place or '…………'}, en autant d'exemplaires originaux que de "
        "parties, chacune reconnaissant avoir reçu le sien."
    )
    width, height = _PAGE_MM
    for index, (role, name) in enumerate(names[:MAX_SIGNERS]):
        signature, date = _fields(index, 0)
        pdf.set_font(FONT, "B", 9)
        pdf.set_xy(signature.x * width / 100, (signature.y - 4) * height / 100)
        pdf.cell(0, 5, f"{role} : {name}")
        pdf.set_draw_color(160)
        for field in (signature, date):
            pdf.rect(
                field.x * width / 100,
                field.y * height / 100,
                field.width * width / 100,
                field.height * height / 100,
            )
        pdf.set_font(FONT, "", 7)
        pdf.set_xy(date.x * width / 100, (date.y + date.height) * height / 100)
        pdf.cell(0, 4, "Date")
    pdf.set_draw_color(0)


def page_count(pdf: bytes) -> int:
    return len(_PAGE_RE.findall(pdf))


def signers_of(lease: Lease, landlord_email: str) -> list[tuple[str, str, str]]:
    """(role, name, email) of the landlord then of each tenant."""
    if not landlord_email:
        raise SignatureError(
            _("Enter your email address in your settings: you sign as the landlord.")
        )
    missing = [tenant.name for tenant in lease.tenants if not tenant.email]
    if missing:
        raise SignatureError(
            _("No email address for %(names)s.") % {"names": ", ".join(missing)}
        )
    if not lease.tenants:
        raise SignatureError(_("The lease has no tenant."))
    signers = [("Bailleur", landlord_of(lease.property).name, landlord_email)]
    signers += [("Locataire", t.name, t.email) for t in lease.tenants]
    if len(signers) > MAX_SIGNERS:
        raise SignatureError(
            _("At most %(count)d people can sign electronically.")
            % {"count": MAX_SIGNERS}
        )
    return signers


def request_signature(
    target: Lease | Inventory,
    *,
    title: str,
    pdf: bytes,
    signers: list[tuple[str, str, str]],
    client: Documenso | None = None,
) -> SignatureRequest:
    """Send *pdf* to the *signers*; the request, with the PDF sent attached."""
    client = client or Documenso()
    last_page = page_count(pdf)
    envelope_id = client.send(
        title=title,
        pdf=pdf,
        signers=[
            Signer(name, email, _fields(index, last_page))
            for index, (_role, name, email) in enumerate(signers)
        ],
        external_id=f"glad-{target._meta.model_name}-{target.pk}",
        subject=f"Signature : {title}",
        message="Merci de relire et de signer ce document.",
    )
    with transaction.atomic():
        signature = SignatureRequest.objects.create(
            target=target,
            title=title,
            external_id=envelope_id,
            signers=[
                {"name": name, "email": email, "status": "pending", "signed_at": None}
                for _role, name, email in signers
            ],
        )
        attach_pdf(
            signature,
            pdf,
            filename=f"{title}.pdf",
            title=title,
            kind=Document.Kind.OTHER,
        )
    return signature


def lease_of(target) -> Lease:
    return target if isinstance(target, Lease) else target.lease


def _complete(signature: SignatureRequest, pdf: bytes) -> None:
    target = signature.target
    lease = lease_of(target)
    is_lease = isinstance(target, Lease)
    with transaction.atomic():
        document = attach_pdf(
            lease,
            pdf,
            filename=f"{signature.title} (signé).pdf",
            title=f"{signature.title} (signé)",
            kind=Document.Kind.LEASE if is_lease else Document.Kind.INVENTORY,
        )
        signature.status = SignatureRequest.Status.COMPLETED
        signature.completed_at = timezone.now()
        signature.signed_document = document
        signature.save()
        if is_lease and lease.signed_date is None:
            lease.signed_date = datetime.date.today()
            lease.save(update_fields=["signed_date", "updated_at"])
        if isinstance(target, Inventory):
            target.status = Inventory.Status.SIGNED
            target.save(update_fields=["status", "updated_at"])
    notify(
        "signature_completed",
        Event(
            key=str(signature.pk),
            title=_("Signed by everyone: %(title)s") % {"title": signature.title},
            url=reverse("rental:lease_detail", kwargs={"pk": lease.pk}),
        ),
    )


def refresh(signature: SignatureRequest, client: Documenso | None = None) -> None:
    """Update a pending request from the provider; store the signed PDF once done."""
    client = client or Documenso()
    envelope = client.envelope(signature.external_id)
    signature.signers = [
        {
            "name": recipient.get("name", ""),
            "email": recipient.get("email", ""),
            "status": str(recipient.get("signingStatus", "")).lower(),
            "signed_at": recipient.get("signedAt"),
        }
        for recipient in envelope.get("recipients", [])
    ]
    status = envelope.get("status")
    if status == "COMPLETED":
        signature.save(update_fields=["signers", "updated_at"])
        _complete(signature, client.download_signed(envelope))
        return
    if status == "REJECTED":
        signature.status = SignatureRequest.Status.REJECTED
    signature.save()


def has_pending() -> bool:
    return SignatureRequest.objects.filter(
        status=SignatureRequest.Status.PENDING
    ).exists()


def poll_signatures() -> str:
    """Refresh every pending signature request (periodic job).

    A request the provider cannot answer keeps its error and the others are
    still checked; the job fails when none could be.
    """
    client = Documenso()
    pending = list(
        SignatureRequest.objects.filter(status=SignatureRequest.Status.PENDING)
    )
    finished = failed = 0
    last_error = ""
    for signature in pending:
        try:
            refresh(signature, client)
        except DocumensoError as exc:
            failed += 1
            last_error = signature.error = str(exc)
            signature.save(update_fields=["error", "updated_at"])
            continue
        finished += signature.status != SignatureRequest.Status.PENDING
    if pending and failed == len(pending):
        raise DocumensoError(f"No signature request could be checked: {last_error}")
    return f"{len(pending)} request(s) checked, {finished} finished, {failed} failed"
