"""Tests for property/services/geocoding.py."""

from unittest.mock import patch

import httpx

from property.services.geocoding import lookup_cadastral_parcel, search_addresses


def _mock_response(status_code=200, json_data=None, text=""):
    """Build an httpx.Response that works with raise_for_status()."""
    request = httpx.Request("GET", "https://test.example/")
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=request)
    return httpx.Response(status_code, text=text, request=request)


# ── search_addresses ──────────────────────────────────────────────────────────


class TestSearchAddresses:
    def test_empty_query_returns_empty_list(self):
        assert search_addresses("") == []
        assert search_addresses("   ") == []

    @patch("property.services.geocoding.httpx.get")
    def test_returns_parsed_results(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "label": "10 Rue de Rivoli, 75001 Paris",
                            "housenumber": "10",
                            "street": "Rue de Rivoli",
                            "postcode": "75001",
                            "city": "Paris",
                            "citycode": "75101",
                        },
                        "geometry": {"coordinates": [2.360, 48.856]},
                    },
                    {
                        "properties": {
                            "label": "Rue de Rivoli, 75001 Paris",
                            "name": "Rue de Rivoli",
                            "postcode": "75001",
                            "city": "Paris",
                            "citycode": "75101",
                        },
                        "geometry": {"coordinates": [2.361, 48.857]},
                    },
                ]
            },
        )

        results = search_addresses("rue de rivoli")

        assert len(results) == 2
        assert results[0]["label"] == "10 Rue de Rivoli, 75001 Paris"
        assert results[0]["street_number"] == "10"
        assert results[0]["street_name"] == "Rue de Rivoli"
        assert results[0]["postal_code"] == "75001"
        assert results[0]["city"] == "Paris"
        assert results[0]["insee_code"] == "75101"
        assert results[0]["latitude"] == 48.856
        assert results[0]["longitude"] == 2.360
        # Second result uses "name" as fallback for "street"
        assert results[1]["street_name"] == "Rue de Rivoli"

    @patch("property.services.geocoding.httpx.get")
    def test_http_error_returns_empty(self, mock_get):
        mock_get.side_effect = httpx.HTTPError("boom")
        assert search_addresses("test") == []

    @patch("property.services.geocoding.httpx.get")
    def test_invalid_json_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(200, text="not json")
        assert search_addresses("test") == []

    @patch("property.services.geocoding.httpx.get")
    def test_missing_coordinates_handled(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "label": "Somewhere",
                            "postcode": "75001",
                            "city": "Paris",
                            "citycode": "75101",
                        },
                        "geometry": {},
                    }
                ]
            },
        )
        results = search_addresses("somewhere")
        assert len(results) == 1
        assert results[0]["latitude"] is None
        assert results[0]["longitude"] is None

    @patch("property.services.geocoding.httpx.get")
    def test_no_features_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(200, json_data={"features": []})
        assert search_addresses("nowhere") == []


# ── lookup_cadastral_parcel ───────────────────────────────────────────────────


class TestLookupCadastralParcel:
    @patch("property.services.geocoding.httpx.get")
    def test_returns_parcel_info(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "section": "AR",
                            "numero": "0042",
                            "code_insee": "75114",
                            "com_abs": "000",
                        }
                    }
                ]
            },
        )

        result = lookup_cadastral_parcel(48.832, 2.327, insee_code="75114")

        assert result is not None
        assert result["section"] == "000AR"
        assert result["numero"] == "0042"
        assert result["insee_code"] == "75114"
        # Only one call when the exact point returns a result
        assert mock_get.call_count == 1

    @patch("property.services.geocoding.httpx.get")
    def test_returns_parcel_info_with_non_zero_prefix(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "section": "AR",
                            "numero": "0042",
                            "code_insee": "75114",
                            "com_abs": "003",
                        }
                    }
                ]
            },
        )

        result = lookup_cadastral_parcel(48.832, 2.327, insee_code="75114")

        assert result is not None
        assert result["section"] == "003AR"

    @patch("property.services.geocoding.httpx.get")
    def test_returns_parcel_info_without_com_abs(self, mock_get):
        """When com_abs is missing, defaults to '000' prefix."""
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "section": "AR",
                            "numero": "0042",
                            "code_insee": "75114",
                        }
                    }
                ]
            },
        )

        result = lookup_cadastral_parcel(48.832, 2.327, insee_code="75114")

        assert result is not None
        assert result["section"] == "000AR"

    @patch("property.services.geocoding.httpx.get")
    def test_no_features_returns_none(self, mock_get):
        # Both exact and buffered queries return empty
        mock_get.return_value = _mock_response(200, json_data={"features": []})
        assert lookup_cadastral_parcel(48.8, 2.3) is None
        # Two calls: exact point then buffered fallback
        assert mock_get.call_count == 2

    @patch("property.services.geocoding.httpx.get")
    def test_http_error_returns_none(self, mock_get):
        mock_get.side_effect = httpx.HTTPError("boom")
        assert lookup_cadastral_parcel(48.8, 2.3) is None
        assert mock_get.call_count == 2

    @patch("property.services.geocoding.httpx.get")
    def test_invalid_json_returns_none(self, mock_get):
        mock_get.return_value = _mock_response(200, text="bad")
        assert lookup_cadastral_parcel(48.8, 2.3) is None
        assert mock_get.call_count == 2

    @patch("property.services.geocoding.httpx.get")
    def test_falls_back_to_insee_param(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "section": "AB",
                            "numero": "0010",
                        }
                    }
                ]
            },
        )

        result = lookup_cadastral_parcel(45.7, 4.8, insee_code="69382")
        assert result is not None
        assert result["insee_code"] == "69382"
        assert result["section"] == "000AB"

    @patch("property.services.geocoding.httpx.get")
    def test_buffered_fallback_finds_nearest_parcel(self, mock_get):
        # First call (exact point) returns empty, second (buffered) returns a parcel
        empty_response = _mock_response(200, json_data={"features": []})
        parcel_response = _mock_response(
            200,
            json_data={
                "features": [
                    {
                        "properties": {
                            "section": "DH",
                            "numero": "0204",
                            "code_insee": "49007",
                        }
                    }
                ]
            },
        )
        mock_get.side_effect = [empty_response, parcel_response]

        result = lookup_cadastral_parcel(47.468431, -0.554123, insee_code="49007")

        assert result is not None
        assert result["section"] == "000DH"
        assert result["numero"] == "0204"
        assert result["insee_code"] == "49007"
        assert mock_get.call_count == 2

        # Verify the second call used a Polygon geom
        second_call_params = mock_get.call_args_list[1].kwargs.get("params", {})
        geom = second_call_params.get("geom", "")
        assert '"Polygon"' in geom

    @patch("property.services.geocoding.httpx.get")
    def test_buffered_fallback_passes_insee_code(self, mock_get):
        empty_response = _mock_response(200, json_data={"features": []})
        parcel_response = _mock_response(
            200,
            json_data={"features": [{"properties": {"section": "A", "numero": "1"}}]},
        )
        mock_get.side_effect = [empty_response, parcel_response]

        lookup_cadastral_parcel(48.8, 2.3, insee_code="75114")

        second_call_params = mock_get.call_args_list[1].kwargs.get("params", {})
        assert second_call_params.get("code_insee") == "75114"

    @patch("property.services.geocoding.httpx.get")
    def test_buffered_fallback_uses_limit(self, mock_get):
        empty_response = _mock_response(200, json_data={"features": []})
        parcel_response = _mock_response(
            200,
            json_data={"features": [{"properties": {"section": "A", "numero": "1"}}]},
        )
        mock_get.side_effect = [empty_response, parcel_response]

        lookup_cadastral_parcel(48.8, 2.3)

        second_call_params = mock_get.call_args_list[1].kwargs.get("params", {})
        assert second_call_params.get("_limit") == 1

    @patch("property.services.geocoding.httpx.get")
    def test_buffered_fallback_http_error_returns_none(self, mock_get):
        # First call succeeds with empty, second call fails
        empty_response = _mock_response(200, json_data={"features": []})
        mock_get.side_effect = [empty_response, httpx.HTTPError("boom")]

        assert lookup_cadastral_parcel(48.8, 2.3) is None

    @patch("property.services.geocoding.httpx.get")
    def test_buffered_fallback_invalid_json_returns_none(self, mock_get):
        empty_response = _mock_response(200, json_data={"features": []})
        bad_response = _mock_response(200, text="bad")
        mock_get.side_effect = [empty_response, bad_response]

        assert lookup_cadastral_parcel(48.8, 2.3) is None
