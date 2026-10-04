"""Download official index series (IRL, consumer prices) from the INSEE BDM API.

The BDM SDMX endpoint is public and needs no API key. Its XML answer lists one
``<Obs TIME_PERIOD="2026-Q2" OBS_VALUE="148.37" DATE_JO="2026-07-12"/>`` element
per period; the attributes are read with a regular expression so that no XML
parser is fed with remote content.
"""

import datetime
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx
from django.db import transaction

from base.models import EconomicIndex, EconomicIndexValue

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_SERIES_URL = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{idbank}"

#: INSEE series identifiers ("idbank").
IDBANKS: dict[str, str] = {
    # Indice de référence des loyers, quarterly.
    EconomicIndex.IRL: "001515333",
    # Consumer price index, base 2025, all households, France, excluding
    # tobacco (the index used for legal indexations), monthly.
    EconomicIndex.CPI: "011814056",
}

_OBS_RE = re.compile(r"<Obs\s([^>]*?)/?>")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


class InseeError(Exception):
    """Raised when a series cannot be downloaded or parsed."""


@dataclass(frozen=True)
class Observation:
    """One value of a series."""

    period: datetime.date
    value: Decimal
    published_on: datetime.date | None


def parse_period(raw: str) -> datetime.date | None:
    """First day of an INSEE period (``2026-Q2`` or ``2026-08``), None if unknown."""
    if match := _QUARTER_RE.match(raw):
        return datetime.date(int(match[1]), (int(match[2]) - 1) * 3 + 1, 1)
    if match := _MONTH_RE.match(raw):
        month = int(match[2])
        if 1 <= month <= 12:
            return datetime.date(int(match[1]), month, 1)
    return None


def parse_observations(payload: str) -> list[Observation]:
    """Extract the observations of an SDMX answer, skipping invalid ones."""
    observations = []
    for obs in _OBS_RE.finditer(payload):
        attrs = dict(_ATTR_RE.findall(obs[1]))
        period = parse_period(attrs.get("TIME_PERIOD", ""))
        try:
            value = Decimal(attrs.get("OBS_VALUE", ""))
        except InvalidOperation:
            continue
        if period is None or not value.is_finite():
            continue
        try:
            published_on = datetime.date.fromisoformat(attrs.get("DATE_JO", ""))
        except ValueError:
            published_on = None
        observations.append(Observation(period, value, published_on))
    return observations


def fetch_series(index: str, start: datetime.date | None = None) -> list[Observation]:
    """Download the observations of *index*, from *start* when given."""
    params = {}
    if start is not None:
        params["startPeriod"] = (
            f"{start.year}-Q{(start.month - 1) // 3 + 1}"
            if index == EconomicIndex.IRL
            else start.strftime("%Y-%m")
        )
    try:
        response = httpx.get(
            _SERIES_URL.format(idbank=IDBANKS[index]),
            params=params,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("INSEE download failed for %s", index, exc_info=True)
        raise InseeError(str(exc)) from exc
    observations = parse_observations(response.text)
    if not observations:
        raise InseeError(f"No observation in the INSEE answer for {index}")
    return observations


def refresh_index(index: str) -> int:
    """Download the missing and revised values of *index*; return the rows written.

    Only the periods from the last stored one are requested, so revisions of
    the latest value are picked up while older history is left untouched.
    """
    last = EconomicIndexValue.objects.filter(index=index).order_by("-period").first()
    observations = fetch_series(index, start=last.period if last else None)
    with transaction.atomic():
        for obs in observations:
            EconomicIndexValue.objects.update_or_create(
                index=index,
                period=obs.period,
                defaults={"value": obs.value, "published_on": obs.published_on},
            )
    return len(observations)
