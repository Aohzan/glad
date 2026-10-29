"""
Dated rules of the French residential lease (loi n° 89-462 du 6 juillet 1989).

Every constant carries the legal source it comes from so that a human can
cross-check the value. Update this module, and only this module, when a law
changes a rule.
"""

import datetime

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
