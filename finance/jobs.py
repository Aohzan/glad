"""Periodic jobs of the finance app (see ``base.scheduler``)."""

import datetime
import logging
import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    QuoteSnapshot,
)
from finance.services.market_data import MarketDataError, fetch_daily_closes

logger = logging.getLogger(__name__)

#: Pause between two securities, to stay polite with Yahoo Finance.
REQUEST_PAUSE_SECONDS = 1.0
#: Market closes older than this are deleted.
KEEP_DAYS = 400


def live_data_allowed() -> bool:
    """Whether a household member allows the market data lookups."""
    return (
        get_user_model()
        .objects.filter(is_active=True, profile__live_data_enabled=True)
        .exclude(profile__is_child=True)
        .exists()
    )


#: Outcomes of the automatic update of a holding.
UPDATED, CONVERTED, NO_RATE, SKIPPED = "updated", "converted", "no_rate", "skipped"


class ExchangeRates:
    """Daily exchange rates from Yahoo Finance, fetched once per pair and run."""

    def __init__(self) -> None:
        self._closes: dict[str, list] = {}

    def rate(self, source: str, target: str, date: datetime.date) -> Decimal | None:
        """Rate converting *source* into *target* at the close of *date* or before."""
        symbol = f"{source}{target}=X"
        if symbol not in self._closes:
            try:
                points, _currency = fetch_daily_closes(symbol)
            except MarketDataError as exc:
                logger.warning("%s", exc)
                points = []
            self._closes[symbol] = points
        candidates = [p for p in self._closes[symbol] if p.date <= date]
        return candidates[-1].price if candidates else None


def _update_holding(
    holding: InvestmentAccountHolding,
    date: datetime.date,
    close: Decimal,
    currency: str,
    rates: ExchangeRates,
) -> str:
    """Value *holding* at *close* on *date*, unless a value already exists that day.

    A security quoted in another currency than its account (Yahoo often
    resolves the ISIN of a European ETF to its USD listing) is converted with
    the exchange rate of the day.
    """
    account_currency = holding.account.currency
    outcome = UPDATED
    if currency != account_currency:
        rate = rates.rate(currency, account_currency, date)
        if rate is None:
            logger.warning(
                "No %s/%s rate for %s: not updated",
                currency,
                account_currency,
                holding.isin,
            )
            return NO_RATE
        close *= rate
        outcome = CONVERTED
    if InvestmentAccountHoldingHistory.objects.filter(
        holding=holding, valuation_date__date=date
    ).exists():
        return SKIPPED  # a value entered by hand that day wins
    quantity = holding.get_quantity()
    if not quantity:
        return SKIPPED
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(close * quantity, account_currency),
        quantity=quantity,
        valuation_date=datetime.datetime.combine(date, datetime.time.min),
    )
    return outcome


def refresh_security_prices() -> str:
    """Store the daily closes of the held securities and update the holdings.

    Every security with an ISIN gets its closes stored (for the drop alerts);
    only the holdings set to ``auto_update_price`` get a new value.
    """
    if not live_data_allowed():
        return "Live market data is disabled"
    holdings = list(
        InvestmentAccountHolding.objects.filter(is_active=True, account__is_active=True)
        .exclude(isin__isnull=True)
        .exclude(isin="")
        .select_related("account")
    )
    isins = sorted({h.isin for h in holdings if h.isin})
    failures: list[str] = []
    outcomes: list[str] = []
    rates = ExchangeRates()
    for index, isin in enumerate(isins):
        if index:
            time.sleep(REQUEST_PAUSE_SECONDS)
        try:
            points, currency = fetch_daily_closes(isin)
        except MarketDataError as exc:
            logger.warning("%s", exc)
            failures.append(isin)
            continue
        with transaction.atomic():
            for point in points:
                QuoteSnapshot.objects.update_or_create(
                    isin=isin,
                    date=point.date,
                    defaults={"close": point.price, "currency": currency},
                )
            if not points:
                continue
            latest = points[-1]
            for holding in holdings:
                if holding.isin == isin and holding.auto_update_price:
                    outcomes.append(
                        _update_holding(
                            holding, latest.date, latest.price, currency, rates
                        )
                    )
    QuoteSnapshot.objects.filter(
        date__lt=datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)
    ).delete()
    if isins and len(failures) == len(isins):
        raise MarketDataError(f"No price could be fetched ({', '.join(failures)})")
    summary = (
        f"{len(isins) - len(failures)}/{len(isins)} securities, "
        f"{outcomes.count(UPDATED) + outcomes.count(CONVERTED)} holding(s) updated"
    )
    if converted := outcomes.count(CONVERTED):
        summary += f" ({converted} converted from another currency)"
    if no_rate := outcomes.count(NO_RATE):
        summary += f", {no_rate} without exchange rate"
    if failures:
        summary += f"; failed: {', '.join(failures)}"
    return summary
