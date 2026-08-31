"""Address autocomplete (BAN) and cadastral parcel lookup (IGN APICarto) services."""

import json
import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_BAN_SEARCH_URL = "https://api-adresse.data.gouv.fr/search/"
_APICARTO_PARCELLE_URL = "https://apicarto.ign.fr/api/cadastre/parcelle"

_FALLBACK_BUFFER_DEG = 0.0002


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
    if insee_code:
        params["code_insee"] = insee_code

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
    if insee_code:
        params["code_insee"] = insee_code

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
        "insee_code": properties.get("code_insee") or insee_code,
    }
