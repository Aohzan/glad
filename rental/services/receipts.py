"""Rent receipts: the quittance of a fully paid period, a receipt otherwise.

The PDF is written in French: it is a French legal document for the tenant.
"""

import datetime

from django.utils import formats, translation
from djmoney.money import Money

from base.models import Document
from base.services.documents import attach_pdf
from base.services.pdf import FONT, BasePdf, money
from property.models import Lease
from rental.models import RentReceipt
from rental.services.landlord import landlord_of
from rental.services.payments import Period


def receipt_for(lease: Lease, period: Period) -> RentReceipt:
    """Create or refresh the receipt of *period* from what was paid."""
    currency = str(lease.rent_amount.currency)
    receipt, _created = RentReceipt.objects.update_or_create(
        lease=lease,
        period_start=period.start,
        defaults={
            "period_end": period.end,
            "rent": Money(period.rent, currency),
            "charges": Money(period.charges, currency),
            "paid_amount": Money(min(period.paid, period.expected), currency),
            "paid_date": period.paid_date,
        },
    )
    return receipt


def _date(day: datetime.date) -> str:
    with translation.override("fr"):
        return formats.date_format(day, "j F Y")


def _address(lease: Lease) -> str:
    prop = lease.property
    return prop.full_address or prop.name


def receipt_pdf(receipt: RentReceipt, today: datetime.date | None = None) -> bytes:
    """The quittance (or the receipt of a partial payment) as a PDF."""
    today = today or datetime.date.today()
    lease = receipt.lease
    landlord = landlord_of(lease.property)
    tenants = " et ".join(t.name for t in lease.tenants) or lease.name
    period = f"du {_date(receipt.period_start)} au {_date(receipt.period_end)}"

    pdf = BasePdf()
    pdf.add_page()
    pdf.heading(
        f"Quittance de loyer n° {receipt.number}"
        if receipt.is_full
        else f"Reçu de paiement partiel n° {receipt.number}"
    )
    pdf.set_font(FONT, "", 9.5)
    pdf.multi_cell(
        90,
        5,
        f"Bailleur\n{landlord.name}\n{landlord.address}",
        new_x="RIGHT",
        new_y="TOP",
    )
    pdf.multi_cell(
        0,
        5,
        f"Locataire\n{tenants}\n{_address(lease)}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    pdf.subheading(f"Logement : {_address(lease)}")
    pdf.subheading(f"Période : {period}")
    pdf.ln(2)
    rows = [
        ["Loyer hors charges", money(receipt.rent.amount)],
        ["Charges", money(receipt.charges.amount)],
        ["Total dû", money(receipt.total.amount)],
        ["Montant reçu", money(receipt.paid_amount.amount)],
    ]
    pdf.simple_table(["Détail", "Montant"], rows, [130, 50], bold_rows={2, 3})
    received = money(receipt.paid_amount.amount)
    paid_on = f" le {_date(receipt.paid_date)}" if receipt.paid_date else ""
    if receipt.is_full:
        pdf.paragraph(
            f"Je soussigné(e) {landlord.name}, bailleur du logement désigné "
            f"ci-dessus, déclare avoir reçu de {tenants} la somme de {received}"
            f"{paid_on}, au titre du loyer et des charges de la période {period}, "
            "et lui en donne quittance, sous réserve de tous mes droits."
        )
    else:
        pdf.paragraph(
            f"Je soussigné(e) {landlord.name}, bailleur du logement désigné "
            f"ci-dessus, déclare avoir reçu de {tenants} la somme de {received}"
            f"{paid_on}, en paiement partiel du loyer et des charges de la "
            f"période {period}. Il reste dû "
            f"{money(receipt.total.amount - receipt.paid_amount.amount)}. "
            "Ce reçu ne vaut pas quittance."
        )
    pdf.ln(4)
    pdf.paragraph(f"Fait le {_date(today)}.")
    pdf.paragraph(landlord.name)
    if receipt.is_full:
        pdf.note(
            "Cette quittance annule les reçus de paiement partiel de la même "
            "période. Le paiement du présent terme n'emporte pas présomption de "
            "paiement des termes antérieurs. La quittance est délivrée gratuitement "
            "(article 21 de la loi n° 89-462 du 6 juillet 1989)."
        )
    return pdf.render()


def store_receipt_pdf(receipt: RentReceipt, user=None) -> Document:
    """The receipt PDF stored as a document of the lease, to attach to an email."""
    return attach_pdf(
        receipt.lease,
        receipt_pdf(receipt),
        filename=receipt.filename,
        title=receipt.filename.removesuffix(".pdf"),
        kind=Document.Kind.RECEIPT,
        user=user,
    )
