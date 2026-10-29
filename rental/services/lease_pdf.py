"""The lease as a PDF, following the standard contract of the décret n° 2015-587.

The document is written in French: it is the contract signed with the tenant.
What Glad does not know is left as a dotted line to fill in by hand; read the
draft before having it signed.
"""

import datetime

from django.utils import formats, translation

from base.services.pdf import BasePdf, money
from property.models import Lease, Property
from rental import rules
from rental.services.landlord import landlord_of
from rental.services.signature import add_signature_page

BLANK = "…………………………"

_KINDS = {
    Lease.LeaseType.EMPTY: "Contrat de location — logement nu",
    Lease.LeaseType.FURNISHED: "Contrat de location — logement meublé",
    Lease.LeaseType.STUDENT: "Contrat de location — logement meublé (bail étudiant)",
    Lease.LeaseType.MOBILITY: "Contrat de location — bail mobilité (logement meublé)",
}
_LAWS = {
    Lease.LeaseType.EMPTY: "titre Ier",
    Lease.LeaseType.FURNISHED: "titre Ier bis",
    Lease.LeaseType.STUDENT: "titre Ier bis",
    Lease.LeaseType.MOBILITY: "titre Ier ter",
}
_QUARTERS = {1: "1er", 2: "2e", 3: "3e", 4: "4e"}


def _date(day: datetime.date) -> str:
    with translation.override("fr"):
        return formats.date_format(day, "j F Y")


def _or_blank(value) -> str:
    return str(value) if value not in (None, "") else BLANK


def _area(value) -> str:
    """``22`` rather than ``22.00``; dotted when unknown."""
    if value is None:
        return BLANK
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _habitat(prop: Property) -> str:
    return "individuel" if prop.property_type == Property.HOUSE else "collectif"


def _duration(lease: Lease) -> str:
    months = lease.duration_months or rules.DEFAULT_DURATION_MONTHS.get(
        lease.lease_type
    )
    if months is None:
        return BLANK + " mois"
    if months % 12 == 0:
        years = months // 12
        return f"{years} an{'s' if years > 1 else ''}"
    return f"{months} mois"


def _term(lease: Lease) -> str:
    if lease.lease_type == Lease.LeaseType.MOBILITY:
        return (
            "Le bail mobilité est conclu pour une durée de 1 à 10 mois, non "
            "renouvelable et non reconductible. Il ne peut être prolongé qu'une "
            "fois, par avenant, dans la limite de 10 mois au total."
        )
    if lease.lease_type == Lease.LeaseType.STUDENT:
        return (
            "Le bail étudiant de 9 mois n'est pas reconduit tacitement : il prend "
            "fin à son terme sans formalité."
        )
    return (
        "À défaut de congé donné dans les conditions de forme et de délai prévues "
        "par la loi, le contrat est reconduit tacitement pour la même durée."
    )


def _section(pdf: BasePdf, title: str) -> None:
    pdf.ln(2)
    pdf.subheading(title)


def lease_pdf(lease: Lease) -> bytes:
    """The draft lease, ending with the signature page."""
    prop = lease.property
    landlord = landlord_of(prop)
    tenants = lease.tenants
    guarantors = lease.guarantors
    currency_total = lease.total_rent().amount

    pdf = BasePdf()
    pdf.add_page()
    pdf.heading(_KINDS.get(lease.lease_type, "Contrat de location"))
    pdf.note(
        "Soumis au "
        + _LAWS.get(lease.lease_type, "titre Ier")
        + " de la loi n° 89-462 du 6 juillet 1989 tendant à améliorer les "
        "rapports locatifs. Contrat type défini par le décret n° 2015-587 du "
        "29 mai 2015."
    )

    _section(pdf, "I. Désignation des parties")
    pdf.paragraph(
        f"Le bailleur : {landlord.name or BLANK}, demeurant "
        f"{landlord.address.replace(chr(10), ', ') or BLANK}, désigné ci-après "
        "« le bailleur »."
    )
    for tenant in tenants:
        born = (
            f", né(e) le {_date(tenant.birth_date)} à {_or_blank(tenant.birth_place)}"
            if tenant.birth_date
            else ""
        )
        contact = f", {tenant.email}" if tenant.email else ""
        pdf.paragraph(f"Le locataire : {tenant.name}{born}{contact}.")
    pdf.paragraph("Désignés ci-après « le locataire ».")

    _section(pdf, "II. Objet du contrat")
    pdf.paragraph(
        "Le présent contrat a pour objet la location d'un logement ainsi "
        "déterminé :\n"
        f"– localisation du logement : {prop.full_address or BLANK} ;\n"
        f"– type d'habitat : immeuble {_habitat(prop)} ;\n"
        f"– régime juridique de l'immeuble : {BLANK} ;\n"
        f"– période de construction : {_or_blank(prop.construction_year)} ;\n"
        f"– surface habitable : {_area(prop.floor_area)} m² ;\n"
        f"– nombre de pièces principales : {_or_blank(prop.number_of_rooms)} ;\n"
        f"– autres parties du logement et équipements : {BLANK} ;\n"
        f"– modalité de production de chauffage et d'eau chaude : {BLANK}.\n"
        "Destination des locaux : usage d'habitation, à titre de résidence "
        + (
            "principale du locataire."
            if lease.lease_type != Lease.LeaseType.MOBILITY
            else "temporaire du locataire en formation, études, apprentissage, "
            "stage, service civique, mutation ou mission temporaire, soit : "
            + BLANK
            + "."
        )
    )

    _section(pdf, "III. Date de prise d'effet et durée du contrat")
    pdf.paragraph(
        f"Le contrat prend effet le {_date(lease.start_date)} pour une durée de "
        f"{_duration(lease)}. {_term(lease)}"
    )

    _section(pdf, "IV. Conditions financières")
    revision = ""
    if lease.lease_type != Lease.LeaseType.MOBILITY:
        quarter = _QUARTERS.get(lease.irl_reference_quarter or 0, BLANK)
        revision = (
            " Le loyer est révisé chaque année à la date anniversaire du contrat, "
            "selon la variation de l'indice de référence des loyers (IRL) publié "
            f"par l'INSEE ; trimestre de référence : {quarter} trimestre"
            + (
                f" (valeur {lease.irl_reference_value})."
                if lease.irl_reference_value
                else "."
            )
        )
    pdf.paragraph(
        f"Loyer mensuel hors charges : {money(lease.rent_amount.amount)}."
        + revision
        + (
            " Le logement est situé en zone tendue : le loyer est soumis aux "
            f"règles d'évolution des loyers ; loyer de référence : {BLANK}."
            if prop.is_tight_zone
            else ""
        )
    )
    if lease.charges_mode == Lease.ChargesMode.FLAT:
        charges = (
            f"Charges récupérables : forfait de {money(lease.charges_amount.amount)} "
            "par mois, sans régularisation ultérieure."
        )
    else:
        charges = (
            "Charges récupérables : provision de "
            f"{money(lease.charges_amount.amount)} par mois, régularisée chaque "
            "année au vu des dépenses réelles (décret n° 87-713 du 26 août 1987)."
        )
    pdf.paragraph(charges)
    pdf.paragraph(
        f"Le loyer et les charges, soit {money(currency_total)}, sont payables "
        f"{'mensuellement' if lease.periodicity == Lease.Periodicity.MONTHLY else 'trimestriellement'}"
        f", d'avance, le {lease.payment_day} de chaque "
        f"{'mois' if lease.periodicity == Lease.Periodicity.MONTHLY else 'trimestre'}."
    )

    _section(pdf, "V. Garanties")
    if lease.lease_type == Lease.LeaseType.MOBILITY:
        pdf.paragraph(
            "Aucun dépôt de garantie ne peut être exigé pour un bail mobilité. "
            "Le locataire peut bénéficier de la garantie Visale."
        )
    else:
        pdf.paragraph(
            f"Dépôt de garantie : {money(lease.deposit_amount.amount)}, restitué "
            "dans un délai d'un mois après la remise des clés lorsque l'état des "
            "lieux de sortie est conforme à celui d'entrée, de deux mois dans le "
            "cas contraire, déduction faite des sommes restant dues."
        )
    for guarantor in guarantors:
        guarantee = guarantor.get_guarantee_type_display()
        pdf.paragraph(
            f"Garant : {guarantor.name} ({guarantee}), "
            "selon l'acte annexé au présent contrat."
        )

    if len(tenants) > 1:
        _section(pdf, "VI. Clause de solidarité")
        pdf.paragraph(
            "Les locataires sont tenus solidairement et indivisiblement de "
            "l'exécution des obligations du présent contrat."
        )

    _section(pdf, "VII. Clause résolutoire")
    pdf.paragraph(
        "Le bail sera résilié de plein droit, si bon semble au bailleur : à défaut "
        "de paiement du loyer, des charges ou du dépôt de garantie, six semaines "
        "après un commandement de payer demeuré infructueux ; à défaut "
        "d'assurance des risques locatifs, un mois après un commandement demeuré "
        "infructueux ; en cas de troubles de voisinage constatés par une "
        "décision de justice."
    )

    _section(pdf, "VIII. Honoraires de location")
    pdf.paragraph("Néant : location conclue directement entre les parties.")

    _section(pdf, "IX. Conditions particulières")
    pdf.paragraph(lease.notes or BLANK)

    _section(pdf, "X. Annexes")
    annexes = [
        "le dossier de diagnostic technique : "
        + ", ".join(rules.required_diagnostics(lease, datetime.date.today())),
        (
            "la notice d'information relative aux droits et obligations des "
            "locataires et des bailleurs (arrêté du 29 mai 2015)"
        ),
        "l'état des lieux d'entrée",
    ]
    if lease.is_furnished:
        annexes.append("l'inventaire et l'état détaillé du mobilier")
    if guarantors:
        annexes.append("l'acte de cautionnement")
    annexes.append("le cas échéant, l'extrait du règlement de copropriété")
    pdf.paragraph(
        "Sont annexés au présent contrat :\n– " + " ;\n– ".join(annexes) + "."
    )

    add_signature_page(
        pdf,
        [("Bailleur", landlord.name)] + [("Locataire", t.name) for t in tenants],
        prop.city,
    )
    return pdf.render()
