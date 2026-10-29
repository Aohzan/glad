"""
Dated rules of the French residential lease (loi n° 89-462 du 6 juillet 1989).

Every constant carries the legal source it comes from so that a human can
cross-check the value. Update this module, and only this module, when a law
changes a rule.
"""

import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext_lazy as _

from property.models import Lease

# ── Security deposit ─────────────────────────────────────────────────────────

#: Maximum deposit in months of rent excluding charges: art. 22 (empty),
#: art. 25-6 (furnished, student included) and art. 25-13 (mobility lease,
#: where a deposit is forbidden). Other lease types have no legal cap.
DEPOSIT_MONTHS: dict[str, int] = {
    Lease.LeaseType.EMPTY: 1,
    Lease.LeaseType.FURNISHED: 2,
    Lease.LeaseType.STUDENT: 2,
    Lease.LeaseType.MOBILITY: 0,
}

# ── Duration ─────────────────────────────────────────────────────────────────

#: Legal duration in months: art. 10 (3 years for an individual landlord,
#: 6 for a company), art. 25-7 (1 year furnished, 9 months for a student).
#: A mobility lease lasts 1 to 10 months as agreed (art. 25-14).
DEFAULT_DURATION_MONTHS: dict[str, int] = {
    Lease.LeaseType.EMPTY: 36,
    Lease.LeaseType.FURNISHED: 12,
    Lease.LeaseType.STUDENT: 9,
}

# ── Diagnostics (dossier de diagnostic technique, art. 3-3) ──────────────────

#: Lead exposure (CREP): buildings constructed before 1 January 1949.
LEAD_BUILT_BEFORE = 1949
#: Asbestos (DAPP): building permit issued before 1 July 1997.
ASBESTOS_BUILT_BEFORE = 1997
#: Electricity and gas: installations older than 15 years.
INSTALLATION_AGE_YEARS = 15


def deposit_cap(lease: Lease):
    """Highest legal deposit of *lease* as Money, None when there is no cap."""
    months = DEPOSIT_MONTHS.get(lease.lease_type)
    if months is None:
        return None
    return lease.rent_amount * months


def required_diagnostics(lease: Lease, today: datetime.date) -> list[str]:
    """Diagnostics to annex to *lease*, from the construction year of the property.

    The age of the electricity and gas installations is taken from the
    construction year. Without a known year, every diagnostic is listed.
    """
    year = lease.property.construction_year
    items = [_("Energy performance (DPE)"), _("Natural and technological risks")]
    if year is None or year < LEAD_BUILT_BEFORE:
        items.append(_("Lead exposure (CREP)"))
    if year is None or year <= ASBESTOS_BUILT_BEFORE:
        items.append(_("Asbestos"))
    if year is None or today.year - year > INSTALLATION_AGE_YEARS:
        items.append(_("Electricity and gas installations"))
    return [str(item) for item in items]


# ── Rental applications (décret n° 2015-1437 du 5 novembre 2015) ─────────────

#: Rent and charges above this share of the income are flagged (indicative,
#: the threshold most landlords and insurers use).
EFFORT_RATE_MAX = 33

#: Documents a landlord may ask a candidate for (one per kind is enough).
ALLOWED_APPLICATION_DOCUMENTS = (
    _("An identity document with a photo"),
    _("A proof of address: last rent receipts, tax notice or certificate of residence"),
    _("Proof of the professional situation: employment contract, student card…"),
    _("Proof of the resources: last 3 payslips, last tax notice, pensions…"),
)

#: Documents the landlord must never ask for (annex of the décret).
FORBIDDEN_APPLICATION_DOCUMENTS = (
    _("Bank statements or a certificate of good account keeping"),
    _("A health insurance card or a medical record"),
    _("A marriage certificate, a family record book or a criminal record"),
    _("A photo, other than on the identity document"),
    _("A cheque to book the dwelling or a direct debit authorisation"),
    _(
        "A certificate from the previous landlord that the rent was paid, when "
        "rent receipts can be given"
    ),
)

# ── Inventory of fixtures ────────────────────────────────────────────────────
#
# The rooms and elements are written in French: they end up in the inventory
# signed by the tenant.

#: Elements checked in most rooms.
_SURFACES = ("Murs", "Sol", "Plafond", "Porte", "Fenêtres", "Éclairage", "Prises")

DEFAULT_ROOMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Entrée", (*_SURFACES, "Interphone")),
    ("Séjour", (*_SURFACES, "Chauffage")),
    ("Cuisine", (*_SURFACES, "Évier", "Plan de travail", "Placards", "Hotte")),
    ("Chambre", (*_SURFACES, "Placard", "Chauffage")),
    (
        "Salle de bains",
        (*_SURFACES, "Lavabo", "Douche ou baignoire", "Robinetterie", "Ventilation"),
    ),
    ("WC", ("Murs", "Sol", "Plafond", "Porte", "Cuvette et chasse d'eau")),
)

#: Equipment a furnished dwelling must have (décret n° 2015-981 du 31 juillet
#: 2015), checked in its own room of the inventory.
FURNITURE_ROOM = "Mobilier"
MANDATORY_FURNITURE = (
    "Literie avec couette ou couverture",
    "Occultation des fenêtres des chambres",
    "Plaques de cuisson",
    "Four ou four à micro-ondes",
    "Réfrigérateur avec compartiment congélation",
    "Vaisselle pour les repas",
    "Ustensiles de cuisine",
    "Table et sièges",
    "Étagères de rangement",
    "Luminaires",
    "Matériel d'entretien ménager",
)

#: Meters read in the inventory.
METERS = (
    ("electricity", _("Electricity")),
    ("gas", _("Gas")),
    ("cold_water", _("Cold water")),
    ("hot_water", _("Hot water")),
)


# ── Departure ────────────────────────────────────────────────────────────────

#: Notice of the tenant in months: art. 15 (3 months for an empty dwelling,
#: 1 month in a tight rental zone) and art. 25-8 (1 month when furnished).
#: A mobility lease can be ended with one month of notice (art. 25-12).
TENANT_NOTICE_MONTHS: dict[str, int] = {
    Lease.LeaseType.EMPTY: 3,
    Lease.LeaseType.FURNISHED: 1,
    Lease.LeaseType.STUDENT: 1,
    Lease.LeaseType.MOBILITY: 1,
}
TIGHT_ZONE_NOTICE_MONTHS = 1
#: Notice of the landlord before the end of the term: 6 months (art. 15),
#: 3 months for a furnished dwelling (art. 25-8).
LANDLORD_NOTICE_MONTHS: dict[str, int] = {
    Lease.LeaseType.EMPTY: 6,
    Lease.LeaseType.FURNISHED: 3,
    Lease.LeaseType.STUDENT: 3,
}

#: The deposit is returned within 1 month of the return of the keys when the
#: exit inventory matches the entry one, 2 months otherwise (art. 22).
DEPOSIT_RETURN_MONTHS = 1
DEPOSIT_RETURN_MONTHS_DAMAGED = 2
#: A late return costs 10 % of the monthly rent excluding charges per started
#: month of delay (art. 22).
DEPOSIT_LATE_PENALTY = Decimal("0.10")
#: Share of the deposit that can be kept until the yearly accounts of the
#: co-ownership are approved (art. 22).
COOWNERSHIP_WITHHOLDING_MAX = Decimal("0.20")


def tenant_notice_months(lease: Lease) -> int:
    if lease.lease_type == Lease.LeaseType.EMPTY and lease.property.is_tight_zone:
        return TIGHT_ZONE_NOTICE_MONTHS
    return TENANT_NOTICE_MONTHS.get(lease.lease_type, 3)


def term_end(lease: Lease, today: datetime.date) -> datetime.date | None:
    """Last day of the current term of a lease renewed by tacit agreement."""
    if lease.end_date:
        return lease.end_date
    months = lease.duration_months or DEFAULT_DURATION_MONTHS.get(lease.lease_type)
    if months is None:
        return None
    end = lease.start_date
    while end <= today:
        end += relativedelta(months=months)
    return end - datetime.timedelta(days=1)
