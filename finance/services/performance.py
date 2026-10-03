"""Money-weighted performance of an account: XIRR, real return and benchmark.

- The XIRR (internal rate of return with dates) is the yearly rate that makes the
  value of every cash flow (opening value and deposits invested, current value
  received) sum to zero. Unlike a simple gain percentage it accounts for when
  the money was invested.
- The real return is the XIRR of the flows expressed in today's euros with the
  INSEE consumer price index.
- The benchmark return is the XIRR the same flows would have produced if every
  deposit had bought units of a market index (e.g. an MSCI World ETF).
"""

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.core.cache import cache

from base.models import EconomicIndex, EconomicIndexValue
from finance.services.market_data import MarketDataError, fetch_historical_prices

logger = logging.getLogger(__name__)

#: A performance over a shorter period is not meaningful once annualized.
MIN_DAYS = 90
_MAX_ITERATIONS = 200
_TOLERANCE = 1e-7
_BENCHMARK_CACHE_SECONDS = 60 * 60 * 12

CashFlow = tuple[datetime.date, Decimal]


def _npv(rate: float, flows: list[tuple[float, float]]) -> float:
    return sum(amount / (1 + rate) ** years for years, amount in flows)


def xirr(cash_flows: list[CashFlow]) -> float | None:
    """Yearly rate (0.05 for 5 %) cancelling the net present value of *cash_flows*.

    Negative amounts are invested, positive ones received. Returns None when
    the flows do not change sign or span less than MIN_DAYS.
    """
    flows = [(day, float(amount)) for day, amount in cash_flows if amount]
    if not flows:
        return None
    start = min(day for day, _amount in flows)
    end = max(day for day, _amount in flows)
    if (end - start).days < MIN_DAYS:
        return None
    if not (any(a < 0 for _d, a in flows) and any(a > 0 for _d, a in flows)):
        return None
    timed = [((day - start).days / 365.0, amount) for day, amount in flows]

    # The NPV decreases with the rate when money is invested first: bisect.
    low, high = -0.9999, 10.0
    npv_low, npv_high = _npv(low, timed), _npv(high, timed)
    if npv_low * npv_high > 0:
        return None
    for _ in range(_MAX_ITERATIONS):
        mid = (low + high) / 2
        npv_mid = _npv(mid, timed)
        if abs(npv_mid) < _TOLERANCE or (high - low) < _TOLERANCE:
            return mid
        if npv_low * npv_mid < 0:
            high = mid
        else:
            low, npv_low = mid, npv_mid
    return (low + high) / 2  # pragma: no cover - bisection always converges


def account_cash_flows(account, as_of: datetime.date | None = None) -> list[CashFlow]:
    """Opening value and deposits (invested, negative) and current value (positive)."""
    as_of = as_of or datetime.date.today()
    flows: list[CashFlow] = [(account.opening_date, -account.opening_amount.amount)]
    for deposit in account.deposits.all():
        deposit_date = deposit.deposit_date
        if isinstance(deposit_date, datetime.datetime):
            deposit_date = deposit_date.date()
        if deposit_date <= as_of:
            flows.append((deposit_date, -deposit.amount.amount))
    flows.append((as_of, account.get_value(max_date=as_of).amount))
    return flows


def _cpi_at(values: list[EconomicIndexValue], day: datetime.date) -> Decimal | None:
    """Last CPI published for a month up to *day* (values sorted by period)."""
    found = None
    for value in values:
        if value.period > day:
            break
        found = value.value
    return found


def real_cash_flows(flows: list[CashFlow]) -> list[CashFlow] | None:
    """*flows* expressed in euros of the last flow date, None without CPI data."""
    values = list(
        EconomicIndexValue.objects.filter(index=EconomicIndex.CPI).order_by("period")
    )
    if not values:
        return None
    reference = _cpi_at(values, max(day for day, _amount in flows))
    if reference is None:
        return None
    real = []
    for day, amount in flows:
        cpi = _cpi_at(values, day)
        if cpi is None:
            return None
        real.append((day, amount * reference / cpi))
    return real


@dataclass(frozen=True)
class Performance:
    """Annualized money-weighted returns of an account."""

    xirr: float | None
    real_xirr: float | None

    @property
    def xirr_percent(self) -> float | None:
        """XIRR in percent."""
        return None if self.xirr is None else self.xirr * 100

    @property
    def real_xirr_percent(self) -> float | None:
        """Real XIRR in percent."""
        return None if self.real_xirr is None else self.real_xirr * 100


def account_performance(account) -> Performance:
    """Nominal and real XIRR of an account."""
    flows = account_cash_flows(account)
    real = real_cash_flows(flows)
    return Performance(xirr=xirr(flows), real_xirr=xirr(real) if real else None)


def _price_at(points, day: datetime.date) -> Decimal | None:
    """Last monthly close on or before *day* (points sorted by date)."""
    found = None
    for point in points:
        if point.date > day:
            break
        found = point.price
    return found


def benchmark_xirr(flows: list[CashFlow], symbol: str, currency: str) -> float | None:
    """XIRR of *flows* invested in *symbol* instead, None when not computable.

    Every invested flow buys units at the monthly close of its month, every
    withdrawal sells some; the units left are valued at the last close.
    Raises MarketDataError when the prices cannot be downloaded or are quoted
    in another currency.
    """
    start = min(day for day, _amount in flows)
    end = max(day for day, _amount in flows)
    cache_key = f"finance:benchmark:{symbol}:{start}:{end}"
    cached = cache.get(cache_key)
    if cached is None:
        points, quote_currency = fetch_historical_prices(
            symbol, start.replace(day=1), end + datetime.timedelta(days=1)
        )
        cached = (sorted(points, key=lambda p: p.date), quote_currency)
        cache.set(cache_key, cached, _BENCHMARK_CACHE_SECONDS)
    points, quote_currency = cached
    if quote_currency != currency:
        raise MarketDataError(
            f"{symbol} is quoted in {quote_currency}, not in {currency}"
        )
    units = Decimal(0)
    simulated: list[CashFlow] = []
    for day, amount in flows[:-1]:
        price = _price_at(points, day) or (points[0].price if points else None)
        if not price:
            return None
        units -= amount / price
        simulated.append((day, amount))
    last_price = _price_at(points, end)
    if not last_price:
        return None
    simulated.append((end, units * last_price))
    return xirr(simulated)
