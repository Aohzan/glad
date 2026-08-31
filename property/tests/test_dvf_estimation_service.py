"""Tests for property/services/dvf_estimation.py."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from moneyed import Money

from property.models import Property
from property.services.dvf_estimation import (
    _normalize_section_prefix,
    estimate_property_value,
    fetch_comparable_sales,
)


def _mock_response(status_code=200, json_data=None, text=""):
    """Build an httpx.Response that works with raise_for_status()."""
    request = httpx.Request("GET", "https://test.example/")
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=request)
    return httpx.Response(status_code, text=text, request=request)


# ── fetch_comparable_sales ────────────────────────────────────────────────────


class TestNormalizeSectionPrefix:
    def test_pads_short_section(self):
        assert _normalize_section_prefix("AR") == "000AR"

    def test_pads_single_char_section(self):
        assert _normalize_section_prefix("A") == "0000A"

    def test_already_5_chars_unchanged(self):
        assert _normalize_section_prefix("000AR") == "000AR"

    def test_truncates_longer_value(self):
        assert _normalize_section_prefix("000AR1234") == "000AR"

    def test_strips_whitespace(self):
        assert _normalize_section_prefix("  AR  ") == "000AR"

    def test_non_zero_prefix_preserved(self):
        assert _normalize_section_prefix("003AR") == "003AR"


class TestFetchComparableSales:
    @patch("property.services.dvf_estimation.httpx.get")
    def test_returns_mutations_list(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "mutations": [{"type_local": "Maison", "valeur_fonciere": 300000}]
            },
        )
        result = fetch_comparable_sales("75114", "AR")
        assert len(result) == 1
        assert result[0]["valeur_fonciere"] == 300000

    @patch("property.services.dvf_estimation.httpx.get")
    def test_normalizes_section_in_url(self, mock_get):
        """Short section codes are padded to 5 chars in the API URL."""
        mock_get.return_value = _mock_response(200, json_data={"mutations": []})
        fetch_comparable_sales("75114", "AR")
        called_url = str(mock_get.call_args.args[0])
        assert "/mutations3/75114/000AR" in called_url

    @patch("property.services.dvf_estimation.httpx.get")
    def test_empty_mutations_key(self, mock_get):
        mock_get.return_value = _mock_response(200, json_data={})
        assert fetch_comparable_sales("75114", "AR") == []

    @patch("property.services.dvf_estimation.httpx.get")
    def test_http_error_returns_empty(self, mock_get):
        mock_get.side_effect = httpx.HTTPError("boom")
        assert fetch_comparable_sales("75114", "AR") == []

    @patch("property.services.dvf_estimation.httpx.get")
    def test_invalid_json_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(200, text="bad")
        assert fetch_comparable_sales("75114", "AR") == []


# ── estimate_property_value ───────────────────────────────────────────────────


@pytest.fixture
def property_factory():
    def _make(**kwargs):
        defaults = {
            "name": "Test Property",
            "property_type": Property.HOUSE,
            "buying_value": Money(200000, "EUR"),
            "buying_date": datetime.date(2020, 1, 1),
            "floor_area": Decimal(100),
            "insee_code": "75114",
            "cadastral_section": "AR",
        }
        defaults.update(kwargs)
        return Property(**defaults)

    return _make


class TestEstimatePropertyValue:
    def test_missing_floor_area(self, property_factory):
        prop = property_factory(floor_area=None, total_surface=None)
        result = estimate_property_value(prop)
        assert result.estimated_value is None
        assert result.reason == "missing_floor_area"

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_uses_total_surface_over_floor_area(self, mock_fetch, property_factory):
        """When total_surface is set, it is used instead of floor_area."""
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 120,
            }
            for _ in range(10)
        ]
        prop = property_factory(
            floor_area=Decimal(80),
            total_surface=Decimal(120),
        )
        result = estimate_property_value(prop)
        assert result.comparable_count == 10
        # median price/m² = 300000/120 = 2500
        assert result.median_price_per_sqm == Decimal(2500)
        # 2500 * 120 (total_surface, not floor_area) = 300000
        assert result.estimated_value is not None
        assert result.estimated_value.amount == Decimal(300000)

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_falls_back_to_floor_area_without_total_surface(
        self, mock_fetch, property_factory
    ):
        """When total_surface is None, floor_area is used."""
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            }
            for _ in range(10)
        ]
        prop = property_factory(
            floor_area=Decimal(100),
            total_surface=None,
        )
        result = estimate_property_value(prop)
        assert result.comparable_count == 10
        # 3000 * 100 = 300000
        assert result.estimated_value is not None
        assert result.estimated_value.amount == Decimal(300000)

    def test_missing_cadastral_info(self, property_factory):
        prop = property_factory(insee_code=None)
        result = estimate_property_value(prop)
        assert result.estimated_value is None
        assert result.reason == "missing_cadastral_info"

    def test_unsupported_property_type(self, property_factory):
        prop = property_factory(property_type=Property.LAND)
        result = estimate_property_value(prop)
        assert result.estimated_value is None
        assert result.reason == "unsupported_property_type"

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_no_comparable_sales(self, mock_fetch, property_factory):
        mock_fetch.return_value = []
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.estimated_value is None
        assert result.reason == "no_comparable_sales"
        assert result.total_mutations == 0

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_no_comparable_sales_with_diagnostics(self, mock_fetch, property_factory):
        recent_date = datetime.date.today().isoformat()
        old_date = (
            datetime.date.today() - datetime.timedelta(days=365 * 6)
        ).isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Appartement",
                "date_mutation": recent_date,
                "valeur_fonciere": 200000,
                "surface_reelle_bati": 50,
            },
            {
                "type_local": "Maison",
                "date_mutation": old_date,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": "bad",
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 0,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": None,
                "date_mutation": recent_date,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()  # HOUSE → looks for "Maison"
        result = estimate_property_value(prop)
        assert result.reason == "no_comparable_sales"
        assert result.total_mutations == 5
        assert result.filtered_by_type == 1
        assert result.filtered_by_date == 1
        assert result.filtered_by_invalid == 2

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_successful_estimation(self, mock_fetch, property_factory):
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 400000,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 500000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()
        result = estimate_property_value(prop)

        assert result.estimated_value is not None
        assert result.comparable_count == 3
        # Median price/m² = median(3000, 4000, 5000) = 4000
        assert result.median_price_per_sqm == Decimal(4000)
        # 4000 * 100 m² = 400000
        assert result.estimated_value.amount == Decimal(400000)
        assert str(result.estimated_value.currency) == "EUR"
        assert result.total_mutations == 3
        assert result.filtered_by_type == 0
        assert result.filtered_by_date == 0
        assert result.filtered_by_invalid == 0

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_filters_wrong_type_local(self, mock_fetch, property_factory):
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Appartement",
                "date_mutation": recent_date,
                "valeur_fonciere": 200000,
                "surface_reelle_bati": 50,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()  # HOUSE → looks for "Maison"
        result = estimate_property_value(prop)
        assert result.comparable_count == 1
        assert result.median_price_per_sqm == Decimal(3000)

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_filters_old_mutations(self, mock_fetch, property_factory):
        old_date = (
            datetime.date.today() - datetime.timedelta(days=365 * 6)
        ).isoformat()
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": old_date,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.comparable_count == 1

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_filters_invalid_values(self, mock_fetch, property_factory):
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 0,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 0,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": "not-a-number",
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.comparable_count == 1

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_apartment_type(self, mock_fetch, property_factory):
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Appartement",
                "date_mutation": recent_date,
                "valeur_fonciere": 200000,
                "surface_reelle_bati": 50,
            },
        ]
        prop = property_factory(
            property_type=Property.APARTMENT,
            floor_area=Decimal(50),
        )
        result = estimate_property_value(prop)
        assert result.comparable_count == 1
        assert result.median_price_per_sqm == Decimal(4000)
        assert result.estimated_value is not None
        assert result.estimated_value.amount == Decimal(200000)

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_progressive_window_uses_narrowest_with_enough_data(
        self, mock_fetch, property_factory
    ):
        """10+ recent sales → 8-month window is used, older sales excluded."""
        today = datetime.date.today()
        recent_date = today.isoformat()
        old_date = (today - datetime.timedelta(days=400)).isoformat()  # ~13 months

        mutations = [
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000 + i * 10000,
                "surface_reelle_bati": 100,
            }
            for i in range(10)
        ]
        # 5 older sales that should be excluded by the 8-month window
        mutations += [
            {
                "type_local": "Maison",
                "date_mutation": old_date,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            }
            for _ in range(5)
        ]
        mock_fetch.return_value = mutations
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.comparable_count == 10
        assert result.filtered_by_date == 5

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_progressive_window_expands_to_14_months(
        self, mock_fetch, property_factory
    ):
        """<10 in 8 months but ≥10 in 14 months → 14-month window used."""
        today = datetime.date.today()
        within_8 = (today - datetime.timedelta(days=200)).isoformat()  # ~6.6 months
        within_14 = (today - datetime.timedelta(days=350)).isoformat()  # ~11.5 months
        too_old = (today - datetime.timedelta(days=500)).isoformat()  # ~16 months

        mutations = [
            {
                "type_local": "Maison",
                "date_mutation": within_8,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            }
            for _ in range(5)
        ]
        mutations += [
            {
                "type_local": "Maison",
                "date_mutation": within_14,
                "valeur_fonciere": 350000,
                "surface_reelle_bati": 100,
            }
            for _ in range(5)
        ]
        mutations += [
            {
                "type_local": "Maison",
                "date_mutation": too_old,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            }
            for _ in range(3)
        ]
        mock_fetch.return_value = mutations
        prop = property_factory()
        result = estimate_property_value(prop)
        # 5 (within 8m) + 5 (within 14m) = 10, but 3 too-old excluded
        assert result.comparable_count == 10
        assert result.filtered_by_date == 3

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_progressive_window_falls_back_to_widest(
        self, mock_fetch, property_factory
    ):
        """If no window has ≥10 sales, the widest (60 months) is used."""
        today = datetime.date.today()
        # Spread across windows but never reaching 10
        mutations = []
        for days_ago in [30, 100, 200, 300, 400, 500, 600, 700, 800, 900]:
            mutations.append(
                {
                    "type_local": "Maison",
                    "date_mutation": (
                        today - datetime.timedelta(days=days_ago)
                    ).isoformat(),
                    "valeur_fonciere": 300000,
                    "surface_reelle_bati": 100,
                }
            )
        # A few very old sales (outside 60 months)
        mutations += [
            {
                "type_local": "Maison",
                "date_mutation": (today - datetime.timedelta(days=365 * 6)).isoformat(),
                "valeur_fonciere": 50000,
                "surface_reelle_bati": 100,
            }
            for _ in range(2)
        ]
        mock_fetch.return_value = mutations
        prop = property_factory()
        result = estimate_property_value(prop)
        # 10 within 60 months, 2 too old
        assert result.comparable_count == 10
        assert result.filtered_by_date == 2

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_progressive_window_all_too_old(self, mock_fetch, property_factory):
        """All sales outside the widest window → no_comparable_sales."""
        today = datetime.date.today()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": (today - datetime.timedelta(days=365 * 7)).isoformat(),
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            }
            for _ in range(5)
        ]
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.reason == "no_comparable_sales"
        assert result.filtered_by_date == 5

    @patch("property.services.dvf_estimation.fetch_comparable_sales")
    def test_mutation_without_date_filtered(self, mock_fetch, property_factory):
        """A mutation with correct type but no date is counted as filtered_by_date."""
        recent_date = datetime.date.today().isoformat()
        mock_fetch.return_value = [
            {
                "type_local": "Maison",
                "date_mutation": None,
                "valeur_fonciere": 100000,
                "surface_reelle_bati": 100,
            },
            {
                "type_local": "Maison",
                "date_mutation": recent_date,
                "valeur_fonciere": 300000,
                "surface_reelle_bati": 100,
            },
        ]
        prop = property_factory()
        result = estimate_property_value(prop)
        assert result.comparable_count == 1
        assert result.filtered_by_date == 1
