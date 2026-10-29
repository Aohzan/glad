"""Market data lookups for investment holdings, backed by yfinance."""

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
lazy import yfinance

CACHE_TTL_SECONDS = 900
#: The Yahoo symbol found for an ISIN is remembered this long.
SYMBOL_CACHE_SECONDS = 7 * 24 * 3600
#: Listings tried first among the search results of an ISIN.
LISTED_TYPES = ("ETF", "EQUITY")
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class MarketDataError(Exception):
    """Raised when a market data lookup fails."""


@dataclass
class LiveQuote:
    """A live market quote for a holding, resolved from its ISIN."""

    name: str | None
    price: Decimal
    currency: str
    previous_close: Decimal | None
    day_high: Decimal | None
    day_low: Decimal | None
    year_high: Decimal | None
    year_low: Decimal | None
    fifty_day_average: Decimal | None
    two_hundred_day_average: Decimal | None
    exchange: str | None
    as_of: datetime.datetime


@dataclass
class HoldingAutofillInfo:
    """Metadata used to autofill a holding creation/edit form from its ISIN."""

    code: str | None
    name: str | None
    issuer: str | None
    fees: Decimal | None
    initial_value: Decimal | None
    currency: str | None


def _decimal_or_none(value: object) -> Decimal | None:
    """Convert a numeric fast_info value to Decimal, or None if unavailable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ValueError, TypeError:
        return None


def fetch_live_quote(isin: str) -> LiveQuote:
    """Fetch a live quote for the given ISIN from Yahoo Finance."""
    try:
        ticker = yfinance.Ticker(isin)
        fast_info = ticker.fast_info
        price = _decimal_or_none(fast_info["last_price"])
        currency = fast_info["currency"]
    except Exception as exc:
        raise MarketDataError(
            str(_("Could not fetch market data for ISIN {isin}: {error}")).format(
                isin=isin, error=exc
            )
        ) from exc

    if price is None or not currency:
        raise MarketDataError(
            str(_("No price data available for ISIN {isin}")).format(isin=isin)
        )

    def _fast_info_get(key: str) -> Decimal | None:
        try:
            return _decimal_or_none(fast_info[key])
        except Exception:
            return None

    name = None
    try:
        info = yfinance.utils.get_info_by_isin(isin)
        name = info.get("longname") or info.get("shortname") or None
    except Exception:
        name = None

    exchange: str | None
    try:
        exchange = fast_info["exchange"]
    except Exception:
        exchange = None

    return LiveQuote(
        name=name,
        price=price,
        currency=str(currency),
        previous_close=_fast_info_get("previous_close"),
        day_high=_fast_info_get("day_high"),
        day_low=_fast_info_get("day_low"),
        year_high=_fast_info_get("year_high"),
        year_low=_fast_info_get("year_low"),
        fifty_day_average=_fast_info_get("fifty_day_average"),
        two_hundred_day_average=_fast_info_get("two_hundred_day_average"),
        exchange=exchange,
        as_of=datetime.datetime.now(),
    )


def get_live_quote(isin: str, *, force_refresh: bool = False) -> LiveQuote:
    """Get a live quote for the given ISIN, using a short-lived cache."""
    cache_key = f"finance:live_quote:{isin}"
    if not force_refresh:
        cached_quote = cache.get(cache_key)
        if cached_quote is not None:
            return cached_quote

    quote = fetch_live_quote(isin)
    cache.set(cache_key, quote, CACHE_TTL_SECONDS)
    return quote


def fetch_holding_autofill(isin: str) -> HoldingAutofillInfo:
    """Fetch holding metadata (code, name, issuer, fees, price) from its ISIN."""
    try:
        info = yfinance.Ticker(isin).info
    except Exception as exc:
        raise MarketDataError(
            str(_("Could not fetch data for ISIN {isin}: {error}")).format(
                isin=isin, error=exc
            )
        ) from exc

    code = info.get("symbol") or None
    if not code:
        raise MarketDataError(
            str(_("Could not resolve a ticker symbol for ISIN {isin}")).format(
                isin=isin
            )
        )

    name = info.get("longName") or info.get("shortName") or None
    issuer = info.get("fundFamily") or None

    # ETFs expose the ratio already as a percentage; older mutual fund data
    # (annualReportExpenseRatio) exposes it as a fraction (e.g. 0.0075 = 0.75%).
    fees = None
    net_expense_ratio = info.get("netExpenseRatio")
    if net_expense_ratio is not None:
        fees = _decimal_or_none(net_expense_ratio)
        if fees is not None:
            fees = round(fees, 2)
    else:
        annual_report_expense_ratio = info.get("annualReportExpenseRatio")
        if annual_report_expense_ratio is not None:
            fees = _decimal_or_none(annual_report_expense_ratio)
            if fees is not None:
                fees = round(fees * 100, 2)

    initial_value = _decimal_or_none(
        info.get("currentPrice") or info.get("regularMarketPrice")
    )
    currency = info.get("currency") or None

    return HoldingAutofillInfo(
        code=code,
        name=name,
        issuer=issuer,
        fees=fees,
        initial_value=initial_value,
        currency=currency,
    )


@dataclass
class HistoricalPricePoint:
    """A single monthly closing price point resolved from an ISIN."""

    date: datetime.date
    price: Decimal


def fetch_historical_prices(
    isin: str, start: datetime.date, end: datetime.date
) -> tuple[list[HistoricalPricePoint], str]:
    """Fetch one closing price per month between *start* and *end* for an ISIN."""
    try:
        ticker = yfinance.Ticker(isin)
        history = ticker.history(start=start, end=end, interval="1mo")
        currency = str(ticker.fast_info["currency"])
    except Exception as exc:
        raise MarketDataError(
            str(_("Could not fetch historical data for ISIN {isin}: {error}")).format(
                isin=isin, error=exc
            )
        ) from exc

    if history is None or history.empty:
        raise MarketDataError(
            str(_("No historical data available for ISIN {isin}")).format(isin=isin)
        )

    points = []
    for timestamp, row in history.iterrows():
        price = _decimal_or_none(row["Close"])
        if price is None:
            continue
        points.append(HistoricalPricePoint(date=timestamp.date(), price=price))

    return points, currency


def _search_symbols(isin: str) -> list[str]:
    """Yahoo symbols of the listings of *isin*, the ETFs and equities first."""
    try:
        quotes = yfinance.Search(isin, max_results=10, news_count=0).quotes
    except Exception:
        return []
    listed = [quote for quote in quotes if quote.get("symbol")]
    listed.sort(key=lambda quote: quote.get("quoteType") not in LISTED_TYPES)
    return [quote["symbol"] for quote in listed]


def _closes(symbol: str, days: int):
    """The daily history and currency of *symbol*, None when it has no prices."""
    ticker = yfinance.Ticker(symbol)
    history = ticker.history(period=f"{days}d", interval="1d")
    if history is None or history.empty:
        return None
    return history, str(ticker.fast_info["currency"])


def fetch_daily_closes(
    isin: str, days: int = 45
) -> tuple[list[HistoricalPricePoint], str]:
    """The daily closing prices of the last *days* days for an ISIN, oldest first.

    Yahoo resolves an ISIN to one listing, which may have no prices (a fund
    listed in Stuttgart, for instance): the other listings found by its search
    are then tried, and the one with prices is remembered. An identifier that
    is not an ISIN (a currency pair) is used as it is.
    """
    cache_key = f"market-symbol:{isin}"
    candidates = [cache.get(cache_key) or isin]
    tried: list[str] = []
    errors: list[Exception] = []
    while candidates:
        symbol = candidates.pop(0)
        if symbol in tried:
            continue
        tried.append(symbol)
        try:
            found = _closes(symbol, days)
        except Exception as exc:
            errors.append(exc)
            found = None
        if found is None:
            if len(tried) == 1 and ISIN_PATTERN.match(isin):
                candidates += [*_search_symbols(isin), isin]
            continue
        cache.set(cache_key, symbol, SYMBOL_CACHE_SECONDS)
        history, currency = found
        points = []
        for timestamp, row in history.iterrows():
            price = _decimal_or_none(row["Close"])
            if price is not None and not price.is_nan():
                points.append(HistoricalPricePoint(date=timestamp.date(), price=price))
        return points, currency
    if errors and len(errors) == len(tried):
        raise MarketDataError(
            str(_("Could not fetch historical data for ISIN {isin}: {error}")).format(
                isin=isin, error=errors[-1]
            )
        ) from errors[-1]
    raise MarketDataError(
        str(_("No historical data available for ISIN {isin}")).format(isin=isin)
    )
