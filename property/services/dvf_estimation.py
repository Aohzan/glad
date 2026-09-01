"""DVF (Demandes de Valeur Foncière) comparable-sales estimation service."""

import datetime
import logging
import statistics
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
from moneyed import Money

if TYPE_CHECKING:
    from property.models import Property

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_MUTATIONS_URL = "https://app.dvf.etalab.gouv.fr/api/mutations3/{insee_code}/{section}"
_RECENCY_WINDOWS_MONTHS = (8, 14, 20, 36, 60)
_MIN_COMPARABLE_SALES = 10
_SECTION_PREFIXE_LENGTH = 5

# Maps our internal property types to the DVF "type_local" labels they're comparable to.
_TYPE_LOCAL_BY_PROPERTY_TYPE = {
    "HO": ("Maison",),
    "AP": ("Appartement",),
    "CO": ("Appartement",),
}


@dataclass
class EstimationResult:
    """Result of a DVF-based value estimation attempt."""

    median_price_per_sqm: Decimal | None = None
    comparable_count: int = 0
    estimated_value: Money | None = None
    reason: str | None = None
    # Diagnostic counters explaining why comparable sales may be empty.
    total_mutations: int = 0
    filtered_by_type: int = 0
    filtered_by_date: int = 0
    filtered_by_invalid: int = 0


def _normalize_section_prefix(section: str) -> str:
    """Normalize a cadastral section to the 5-char ``section_prefixe`` expected by DVF.

    DVF stores *section_prefixe* as a 5-character field: a 3-char commune
    prefix (almost always ``"000"``) followed by the 2-char section code
    (e.g. ``"AR"``).  APICarto and manual entry often provide only the
    2-char section, so we left-pad with ``"0"`` when a short value is
    received.
    """
    section = section.strip()
    if len(section) >= _SECTION_PREFIXE_LENGTH:
        return section[:_SECTION_PREFIXE_LENGTH]
    return section.rjust(_SECTION_PREFIXE_LENGTH, "0")


def fetch_comparable_sales(insee_code: str, section: str) -> list[dict]:
    """Fetch raw DVF mutations for a commune + cadastral section."""
    normalized_section = _normalize_section_prefix(section)
    url = _MUTATIONS_URL.format(insee_code=insee_code, section=normalized_section)
    try:
        response = httpx.get(url, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError, ValueError:
        logger.warning(
            "DVF mutations fetch failed for %s/%s",
            insee_code,
            normalized_section,
            exc_info=True,
        )
        return []
    return data.get("mutations") or []


def estimate_property_value(property_obj: Property) -> EstimationResult:
    """Estimate a property's current value from comparable DVF sales.

    The estimation uses ``total_surface`` (actual built surface) when
    available, falling back to ``floor_area`` (Loi Carrez) otherwise.
    DVF reports ``surface_reelle_bati`` which is the actual built surface,
    so comparing with ``total_surface`` gives a more accurate estimate.
    """
    estimation_surface = property_obj.total_surface or property_obj.floor_area
    if not estimation_surface:
        return EstimationResult(reason="missing_floor_area")

    if not property_obj.insee_code or not property_obj.cadastral_section:
        return EstimationResult(reason="missing_cadastral_info")

    type_locals = _TYPE_LOCAL_BY_PROPERTY_TYPE.get(property_obj.property_type)
    if not type_locals:
        return EstimationResult(reason="unsupported_property_type")

    mutations = fetch_comparable_sales(
        property_obj.insee_code, property_obj.cadastral_section
    )

    today = datetime.date.today()

    # Pre-filter: keep only valid comparable sales (correct type + parseable data).
    valid_sales: list[tuple[str, Decimal]] = []
    filtered_by_type = 0
    filtered_by_date = 0
    filtered_by_invalid = 0

    for mutation in mutations:
        if mutation.get("type_local") not in type_locals:
            if mutation.get("type_local"):
                filtered_by_type += 1
            continue
        if not mutation.get("date_mutation"):
            filtered_by_date += 1
            continue
        try:
            value = Decimal(str(mutation.get("valeur_fonciere")))
            surface = Decimal(str(mutation.get("surface_reelle_bati")))
        except TypeError, ValueError, ArithmeticError:
            filtered_by_invalid += 1
            continue
        if value <= 0 or surface <= 0:
            filtered_by_invalid += 1
            continue
        valid_sales.append((mutation["date_mutation"], value / surface))

    # Progressive time windows: try the narrowest first and expand until we
    # have enough comparable sales.  If no window reaches the threshold, fall
    # back to the widest one.
    selected_prices: list[Decimal] = []
    for months in _RECENCY_WINDOWS_MONTHS:
        min_date = (today - datetime.timedelta(days=30 * months)).isoformat()
        selected_prices = [p for d, p in valid_sales if d >= min_date]
        if len(selected_prices) >= _MIN_COMPARABLE_SALES:
            logger.debug(
                "DVF estimation: %d comparable sales found within %d months",
                len(selected_prices),
                months,
            )
            break

    filtered_by_date += len(valid_sales) - len(selected_prices)

    if not selected_prices:
        return EstimationResult(
            reason="no_comparable_sales",
            total_mutations=len(mutations),
            filtered_by_type=filtered_by_type,
            filtered_by_date=filtered_by_date,
            filtered_by_invalid=filtered_by_invalid,
        )

    median_price = statistics.median(selected_prices)
    estimated_value = Money(
        (median_price * Decimal(str(estimation_surface))).quantize(Decimal(1)),
        property_obj.currency,
    )
    return EstimationResult(
        median_price_per_sqm=median_price.quantize(Decimal(1)),
        comparable_count=len(selected_prices),
        estimated_value=estimated_value,
        total_mutations=len(mutations),
        filtered_by_type=filtered_by_type,
        filtered_by_date=filtered_by_date,
        filtered_by_invalid=filtered_by_invalid,
    )
