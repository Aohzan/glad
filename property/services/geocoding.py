"""Address autocomplete (BAN) and cadastral parcel lookup (IGN APICarto) services."""

import json
import logging
from decimal import Decimal

lazy import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_BAN_SEARCH_URL = "https://api-adresse.data.gouv.fr/search/"
_APICARTO_PARCELLE_URL = "https://apicarto.ign.fr/api/cadastre/parcelle"

_FALLBACK_BUFFER_DEG = 0.0002

#: Communes split into arrondissements: (first code, last code, commune code).
#: BAN gives the arrondissement code (75118) while APICarto files the parcels
#: under the commune code (75056), the arrondissement being in ``code_arr``.
_ARRONDISSEMENTS = (
    (75101, 75120, "75056"),  # Paris
    (69381, 69389, "69123"),  # Lyon
    (13201, 13216, "13055"),  # Marseille
)


def search_addresses(query: str, limit: int = 5) -> list[dict]:
    """Search French addresses via the BAN (Base Adresse Nationale) API."""
    query = query.strip()
    if not query:
        return []

    try:
        response = httpx.get(
            _BAN_SEARCH_URL,
            params={"q": query, "limit": limit},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError, ValueError:
        logger.warning("BAN address search failed for query %r", query, exc_info=True)
        return []

    results = []
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates") or [None, None]
        longitude, latitude = coordinates[0], coordinates[1]
        results.append(
            {
                "label": properties.get("label", ""),
                "street_number": properties.get("housenumber"),
                "street_name": properties.get("street") or properties.get("name"),
                "postal_code": properties.get("postcode"),
                "city": properties.get("city"),
                "insee_code": properties.get("citycode"),
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return results


def _apicarto_commune_code(insee_code: str | None) -> str | None:
    """Code under which APICarto files the parcels of *insee_code*.

    An arrondissement of Paris, Lyon or Marseille is replaced by its commune
    code; any other code is returned unchanged.
    """
    if insee_code and insee_code.isdigit():
        number = int(insee_code)
        for first, last, commune in _ARRONDISSEMENTS:
            if first <= number <= last:
                return commune
    return insee_code


def lookup_cadastral_parcel(
    latitude: Decimal | float, longitude: Decimal | float, insee_code: str | None = None
) -> dict | None:
    """Find the cadastral section/parcel number containing the given point.

    If the exact point doesn't fall inside any parcel (e.g. it lands on a
    road or river), retry with a small buffer polygon to find the nearest
    parcel.
    """
    result = _query_apicarto_parcelle(latitude, longitude, insee_code)
    if result is not None:
        return result

    return _query_apicarto_parcelle_buffered(latitude, longitude, insee_code)


def _query_apicarto_parcelle(
    latitude: Decimal | float, longitude: Decimal | float, insee_code: str | None
) -> dict | None:
    """Query APICarto with an exact point intersection."""
    geom = {"type": "Point", "coordinates": [float(longitude), float(latitude)]}
    params: dict = {"geom": json.dumps(geom)}
    commune_code = _apicarto_commune_code(insee_code)
    if commune_code:
        params["code_insee"] = commune_code

    try:
        response = httpx.get(_APICARTO_PARCELLE_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError, ValueError:
        logger.warning(
            "APICarto cadastral lookup failed for (%s, %s)",
            latitude,
            longitude,
            exc_info=True,
        )
        return None

    return _extract_parcel(data, insee_code)


def _query_apicarto_parcelle_buffered(
    latitude: Decimal | float, longitude: Decimal | float, insee_code: str | None
) -> dict | None:
    """Query APICarto with a small buffer polygon to find the nearest parcel."""
    lat = float(latitude)
    lon = float(longitude)
    d = _FALLBACK_BUFFER_DEG
    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - d, lat - d],
                [lon + d, lat - d],
                [lon + d, lat + d],
                [lon - d, lat + d],
                [lon - d, lat - d],
            ]
        ],
    }
    params: dict = {"geom": json.dumps(poly), "_limit": 1}
    commune_code = _apicarto_commune_code(insee_code)
    if commune_code:
        params["code_insee"] = commune_code

    try:
        response = httpx.get(_APICARTO_PARCELLE_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError, ValueError:
        logger.warning(
            "APICarto buffered lookup failed for (%s, %s)",
            latitude,
            longitude,
            exc_info=True,
        )
        return None

    return _extract_parcel(data, insee_code)


def _extract_parcel(data: dict, insee_code: str | None) -> dict | None:
    """Extract section/numero from an APICarto FeatureCollection response.

    The ``section_prefixe`` returned is the 5-character field used by DVF:
    a 3-char commune prefix (``com_abs``, almost always ``"000"``) followed
    by the 2-char section code.

    The returned ``insee_code`` is the one of the arrondissement in Paris,
    Lyon and Marseille (the first 5 characters of ``idu``), as DVF expects,
    and not the commune code APICarto returns in ``code_insee``.
    """
    features = data.get("features") or []
    if not features:
        return None

    properties = features[0].get("properties", {})
    section = properties.get("section") or ""
    com_abs = properties.get("com_abs") or "000"
    section_prefixe = f"{com_abs}{section}" if section else None
    return {
        "section": section_prefixe or section,
        "numero": properties.get("numero"),
        "insee_code": (properties.get("idu") or "")[:5]
        or insee_code
        or properties.get("code_insee"),
    }
