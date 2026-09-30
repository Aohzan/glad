"""Energy performance diagnosis (DPE) rules of the French rental market.

- Loi Climat et Résilience (2021): housing rated G, F then E can no longer be
  rented out as a decent home from 2025, 2028 and 2034 (mainland France).
- Since 24 August 2022, the rent of F and G rated housing cannot be increased
  (no IRL revision, no increase when re-letting).
- A DPE is valid 10 years, except those carried out before 1 July 2021 which
  expired on 31 December 2022 (before 2018) or 31 December 2024.
"""

import datetime
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta

RENTAL_BAN_DATES: dict[str, datetime.date] = {
    "G": datetime.date(2025, 1, 1),
    "F": datetime.date(2028, 1, 1),
    "E": datetime.date(2034, 1, 1),
}
RENT_FREEZE_RATINGS = frozenset({"F", "G"})
DPE_VALIDITY_YEARS = 10
#: The rental ban is flagged as a warning when it is closer than this.
BAN_WARNING_YEARS = 3
EXPIRY_WARNING_DAYS = 180

_OLD_DPE_EXPIRY = (
    (datetime.date(2018, 1, 1), datetime.date(2022, 12, 31)),
    (datetime.date(2021, 7, 1), datetime.date(2024, 12, 31)),
)


def dpe_expiry(dpe_date: datetime.date) -> datetime.date:
    """Last day a DPE carried out on *dpe_date* is valid."""
    for made_before, expires_on in _OLD_DPE_EXPIRY:
        if dpe_date < made_before:
            return expires_on
    return dpe_date + relativedelta(years=DPE_VALIDITY_YEARS, days=-1)


def rent_increase_allowed(rating: str) -> bool:
    """False for F and G rated housing, whose rent is frozen."""
    return rating not in RENT_FREEZE_RATINGS


@dataclass(frozen=True)
class DpeStatus:
    """Rental ban and validity of a property energy rating at a given date."""

    rating: str
    today: datetime.date
    ban_date: datetime.date | None
    expires_on: datetime.date | None

    @property
    def is_banned(self) -> bool:
        """True when the property can no longer be rented out."""
        return self.ban_date is not None and self.ban_date <= self.today

    @property
    def ban_is_near(self) -> bool:
        """True when a future rental ban starts within BAN_WARNING_YEARS."""
        return (
            self.ban_date is not None
            and not self.is_banned
            and self.ban_date <= self.today + relativedelta(years=BAN_WARNING_YEARS)
        )

    @property
    def is_expired(self) -> bool:
        """True when the DPE is no longer valid."""
        return self.expires_on is not None and self.expires_on < self.today

    @property
    def expires_soon(self) -> bool:
        """True when the DPE expires within EXPIRY_WARNING_DAYS."""
        return (
            self.expires_on is not None
            and not self.is_expired
            and (self.expires_on - self.today).days <= EXPIRY_WARNING_DAYS
        )

    @property
    def rent_frozen(self) -> bool:
        """True when the rent cannot be increased."""
        return not rent_increase_allowed(self.rating)

    @property
    def level(self) -> str | None:
        """Bootstrap alert level: danger, warning or None when nothing to flag."""
        if self.is_banned or self.is_expired:
            return "danger"
        if self.ban_is_near or self.expires_soon or self.rent_frozen:
            return "warning"
        return None


def get_dpe_status(
    rating: str,
    dpe_date: datetime.date | None,
    today: datetime.date | None = None,
) -> DpeStatus | None:
    """Status of an energy *rating* (A–G), None when the rating is unknown."""
    if not rating:
        return None
    return DpeStatus(
        rating=rating,
        today=today or datetime.date.today(),
        ban_date=RENTAL_BAN_DATES.get(rating),
        expires_on=dpe_expiry(dpe_date) if dpe_date else None,
    )
