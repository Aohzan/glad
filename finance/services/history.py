"""Account values at many dates, computed from a few bulk queries.

``get_value(max_date=...)`` runs several queries per call, which is far too
slow to draw the history of every account month by month. These helpers load
each history table once and resolve every date in memory, with the same rules
as the ``get_value()`` methods of the models.
"""

import datetime
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue


class _Timeline:
    """Values of one entity sorted by date, read back as of any date."""

    def __init__(self) -> None:
        self.dates: list = []
        self.values: list[Decimal] = []

    def append(self, date, value: Decimal) -> None:
        self.dates.append(date)
        self.values.append(value)

    def at(self, date) -> Decimal | None:
        """Last value dated on or before *date*, None before the first one."""
        index = bisect_right(self.dates, date)
        return self.values[index - 1] if index else None


def _timelines(rows: Iterable[tuple[int, object, Decimal]]) -> dict[int, _Timeline]:
    """Group ``(owner id, date, value)`` rows already sorted by owner and date."""
    timelines: dict[int, _Timeline] = defaultdict(_Timeline)
    for owner_id, date, value in rows:
        timelines[owner_id].append(date, value)
    return timelines


def saving_values_at(
    accounts: Sequence[SavingAccount], dates: Sequence[datetime.date]
) -> dict[int, list[Decimal]]:
    """Value of each saving account at the end of each date, keyed by account id."""
    timelines = _timelines(
        SavingAccountValue.objects.filter(account__in=accounts)
        .order_by("account_id", "value_date")
        .values_list("account_id", "value_date", "value")
    )
    ends_of_day = [datetime.datetime.combine(d, datetime.time.max) for d in dates]
    result = {}
    for account in accounts:
        timeline = timelines.get(account.pk, _Timeline())
        opening = account.opening_value.amount
        result[account.pk] = [
            value if (value := timeline.at(end)) is not None else opening
            for end in ends_of_day
        ]
    return result


def investment_values_at(
    accounts: Sequence[InvestmentAccount], dates: Sequence[datetime.date]
) -> dict[int, list[Decimal]]:
    """Cash plus active holdings of each investment account at each date.

    A holding valuation counts from the midnight of its date, as in
    ``InvestmentAccount.get_value()`` which compares the valuation datetime to
    a date.
    """
    cash = _timelines(
        InvestmentAccountCash.objects.filter(account__in=accounts)
        .order_by("account_id", "value_date")
        .values_list("account_id", "value_date", "value")
    )
    holdings: dict[int, list[InvestmentAccountHolding]] = defaultdict(list)
    for holding in InvestmentAccountHolding.objects.filter(
        account__in=accounts, is_active=True
    ):
        holdings[holding.account_id].append(holding)  # ty: ignore[unresolved-attribute]
    history = _timelines(
        InvestmentAccountHoldingHistory.objects.filter(
            holding__account__in=accounts, holding__is_active=True
        )
        .order_by("holding_id", "valuation_date")
        .values_list("holding_id", "valuation_date", "value")
    )

    midnights = [datetime.datetime.combine(d, datetime.time.min) for d in dates]
    result = {}
    for account in accounts:
        cash_timeline = cash.get(account.pk, _Timeline())
        opening = account.opening_cash_value.amount
        values = []
        for date, midnight in zip(dates, midnights, strict=True):
            cash_value = cash_timeline.at(date)
            total = cash_value if cash_value is not None else opening
            for holding in holdings[account.pk]:
                holding_value = history.get(holding.pk, _Timeline()).at(midnight)
                if holding_value is not None:
                    total += holding_value
                elif holding.initial_valuation_date <= date:
                    total += holding.initial_value.amount
            values.append(total)
        result[account.pk] = values
    return result
