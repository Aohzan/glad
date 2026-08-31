"""Tests for finance/services/market_data.py."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache

from finance.services.market_data import (
    LiveQuote,
    MarketDataError,
    fetch_historical_prices,
    fetch_holding_autofill,
    fetch_live_quote,
    get_live_quote,
)


class _PartialFastInfo(dict):
    """A fast_info-like dict that raises KeyError for some keys."""

    def __init__(self, data, missing_keys):
        super().__init__(data)
        self._missing_keys = missing_keys

    def __getitem__(self, key):
        if key in self._missing_keys:
            raise KeyError(key)
        return super().__getitem__(key)


FULL_FAST_INFO = {
    "last_price": 123.45,
    "currency": "EUR",
    "previous_close": 120.0,
    "day_high": 125.0,
    "day_low": 119.0,
    "year_high": 130.0,
    "year_low": 100.0,
    "fifty_day_average": 122.0,
    "two_hundred_day_average": 115.0,
    "exchange": "PAR",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestFetchLiveQuote:
    """Tests for fetch_live_quote."""

    @patch("finance.services.market_data.yfinance.utils.get_info_by_isin")
    @patch("finance.services.market_data.yfinance.Ticker")
    def test_success_all_fields(self, mock_ticker, mock_get_info):
        mock_ticker.return_value.fast_info = dict(FULL_FAST_INFO)
        mock_get_info.return_value = {"longname": "World ETF", "shortname": "WRLD"}

        quote = fetch_live_quote("LU1681043599")

        assert quote.name == "World ETF"
        assert quote.price == Decimal("123.45")
        assert quote.currency == "EUR"
        assert quote.previous_close == Decimal("120.0")
        assert quote.day_high == Decimal("125.0")
        assert quote.day_low == Decimal("119.0")
        assert quote.year_high == Decimal("130.0")
        assert quote.year_low == Decimal("100.0")
        assert quote.fifty_day_average == Decimal("122.0")
        assert quote.two_hundred_day_average == Decimal("115.0")
        assert quote.exchange == "PAR"

    @patch("finance.services.market_data.yfinance.utils.get_info_by_isin")
    @patch("finance.services.market_data.yfinance.Ticker")
    def test_partial_fields_missing(self, mock_ticker, mock_get_info):
        mock_ticker.return_value.fast_info = _PartialFastInfo(
            FULL_FAST_INFO, missing_keys={"year_high", "year_low", "exchange"}
        )
        mock_get_info.return_value = {"longname": "World ETF"}

        quote = fetch_live_quote("LU1681043599")

        assert quote.price == Decimal("123.45")
        assert quote.year_high is None
        assert quote.year_low is None
        assert quote.exchange is None

    @patch("finance.services.market_data.yfinance.utils.get_info_by_isin")
    @patch("finance.services.market_data.yfinance.Ticker")
    def test_name_resolution_failure_does_not_block_price(
        self, mock_ticker, mock_get_info
    ):
        mock_ticker.return_value.fast_info = dict(FULL_FAST_INFO)
        mock_get_info.side_effect = Exception("search unavailable")

        quote = fetch_live_quote("LU1681043599")

        assert quote.name is None
        assert quote.price == Decimal("123.45")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_missing_price_raises(self, mock_ticker):
        mock_ticker.return_value.fast_info = _PartialFastInfo(
            FULL_FAST_INFO, missing_keys={"last_price"}
        )

        with pytest.raises(MarketDataError):
            fetch_live_quote("INVALID000000")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_ticker_exception_raises_market_data_error(self, mock_ticker):
        mock_ticker.side_effect = Exception("network error")

        with pytest.raises(MarketDataError):
            fetch_live_quote("INVALID000000")


class TestGetLiveQuote:
    """Tests for get_live_quote caching behavior."""

    def _make_quote(self):
        return LiveQuote(
            name="World ETF",
            price=Decimal("123.45"),
            currency="EUR",
            previous_close=None,
            day_high=None,
            day_low=None,
            year_high=None,
            year_low=None,
            fifty_day_average=None,
            two_hundred_day_average=None,
            exchange=None,
            as_of=datetime.datetime.now(),
        )

    @patch("finance.services.market_data.fetch_live_quote")
    def test_caches_result(self, mock_fetch):
        mock_fetch.return_value = self._make_quote()

        get_live_quote("LU1681043599")
        get_live_quote("LU1681043599")

        assert mock_fetch.call_count == 1

    @patch("finance.services.market_data.fetch_live_quote")
    def test_force_refresh_bypasses_cache(self, mock_fetch):
        mock_fetch.return_value = self._make_quote()

        get_live_quote("LU1681043599")
        get_live_quote("LU1681043599", force_refresh=True)

        assert mock_fetch.call_count == 2


class TestFetchHoldingAutofill:
    """Tests for fetch_holding_autofill."""

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_success_etf_with_expense_ratio(self, mock_ticker):
        mock_ticker.return_value.info = {
            "symbol": "CW8",
            "longName": "Amundi MSCI World",
            "fundFamily": "Amundi",
            "annualReportExpenseRatio": 0.0038,
            "currentPrice": 450.5,
            "currency": "EUR",
        }

        autofill = fetch_holding_autofill("LU1681043599")

        assert autofill.code == "CW8"
        assert autofill.name == "Amundi MSCI World"
        assert autofill.issuer == "Amundi"
        assert autofill.fees == Decimal("0.38")
        assert autofill.initial_value == Decimal("450.5")
        assert autofill.currency == "EUR"

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_success_etf_with_net_expense_ratio(self, mock_ticker):
        # Yahoo exposes ETF expense ratios directly as a percentage, unlike
        # the legacy (and now unpopulated) annualReportExpenseRatio fraction.
        mock_ticker.return_value.info = {
            "symbol": "WPEA.PA",
            "longName": "iShares MSCI World Swap PEA UCITS ETF",
            "fundFamily": "BlackRock Asset Management Ireland - ETF",
            "netExpenseRatio": 0.2,
            "regularMarketPrice": 6.948,
            "currency": "EUR",
        }

        autofill = fetch_holding_autofill("IE0002XZSHO1")

        assert autofill.fees == Decimal("0.2")
        assert autofill.initial_value == Decimal("6.948")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_stock_without_expense_ratio(self, mock_ticker):
        mock_ticker.return_value.info = {
            "symbol": "AAPL",
            "shortName": "Apple Inc.",
            "regularMarketPrice": 190.0,
            "currency": "USD",
        }

        autofill = fetch_holding_autofill("US0378331005")

        assert autofill.code == "AAPL"
        assert autofill.name == "Apple Inc."
        assert autofill.issuer is None
        assert autofill.fees is None
        assert autofill.initial_value == Decimal("190.0")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_missing_symbol_raises(self, mock_ticker):
        mock_ticker.return_value.info = {"longName": "Unknown"}

        with pytest.raises(MarketDataError):
            fetch_holding_autofill("INVALID000000")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_ticker_exception_raises_market_data_error(self, mock_ticker):
        mock_ticker.side_effect = Exception("network error")

        with pytest.raises(MarketDataError):
            fetch_holding_autofill("INVALID000000")


class TestFetchHistoricalPrices:
    """Tests for fetch_historical_prices."""

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_success_returns_monthly_points(self, mock_ticker):
        import pandas as pd

        history = pd.DataFrame(
            {"Close": [100.0, 105.5, 110.0]},
            index=pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
        )
        mock_ticker.return_value.history.return_value = history
        mock_ticker.return_value.fast_info = {"currency": "EUR"}

        points, currency = fetch_historical_prices(
            "LU1681043599",
            datetime.date(2025, 1, 1),
            datetime.date(2025, 3, 31),
        )

        assert currency == "EUR"
        assert len(points) == 3
        assert points[0].date == datetime.date(2025, 1, 1)
        assert points[0].price == Decimal("100.0")
        assert points[2].price == Decimal("110.0")

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_empty_history_raises(self, mock_ticker):
        import pandas as pd

        mock_ticker.return_value.history.return_value = pd.DataFrame()
        mock_ticker.return_value.fast_info = {"currency": "EUR"}

        with pytest.raises(MarketDataError):
            fetch_historical_prices(
                "LU1681043599",
                datetime.date(2025, 1, 1),
                datetime.date(2025, 3, 31),
            )

    @patch("finance.services.market_data.yfinance.Ticker")
    def test_ticker_exception_raises_market_data_error(self, mock_ticker):
        mock_ticker.side_effect = Exception("network error")

        with pytest.raises(MarketDataError):
            fetch_historical_prices(
                "INVALID000000",
                datetime.date(2025, 1, 1),
                datetime.date(2025, 3, 31),
            )
