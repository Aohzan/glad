"""Account values at many dates, computed from a few bulk queries.

``get_value(max_date=...)`` runs several queries per call, which is far too
slow to value every account month by month. These classes read the histories
of a set of accounts once, then give the amount ``get_value()`` returns at any
date or datetime without querying the database again.
"""

import datetime
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from base.services.timeline import DatedValues
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue


class SavingValues:
    """Values of saving accounts, read with one query."""

    def __init__(self, accounts: Iterable[SavingAccount]) -> None:
        self._values = DatedValues(
            SavingAccountValue.objects.filter(account__in=accounts)
            .order_by("account_id", "value_date", "pk")
            .values_list("account_id", "value_date", "value")
        )

    def at(self, account: SavingAccount, moment: datetime.date) -> Decimal:
        """Amount of ``account.get_value(max_date=moment)``.

        A date reads the values saved up to the end of that day.
        """
        if not isinstance(moment, datetime.datetime):
            moment = datetime.datetime.combine(moment, datetime.time.max)
        value = self._values.at(account.pk, moment)
        return value if value is not None else account.opening_value.amount


class InvestmentValues:
    """Values of investment accounts, cash and active holdings, read with three queries."""

    def __init__(self, accounts: Iterable[InvestmentAccount]) -> None:
        accounts = list(accounts)
        self._cash = DatedValues(
            InvestmentAccountCash.objects.filter(account__in=accounts)
            .order_by("account_id", "value_date", "pk")
            .values_list("account_id", "value_date", "value")
        )
        self._holdings: dict[int, list[InvestmentAccountHolding]] = defaultdict(list)
        for holding in InvestmentAccountHolding.objects.filter(
            account__in=accounts, is_active=True
        ):
            self._holdings[holding.account_id].append(holding)  # ty: ignore[unresolved-attribute]
        self._history = DatedValues(
            InvestmentAccountHoldingHistory.objects.filter(
                holding__account__in=accounts, holding__is_active=True
            )
            .order_by("holding_id", "valuation_date", "pk")
            .values_list("holding_id", "valuation_date", "value")
        )

    def at(self, account: InvestmentAccount, moment: datetime.date) -> Decimal:
        """Amount of ``account.get_value(max_date=moment)``.

        The cash is read up to the day of *moment*. A holding valuation counts
        from *moment* when it is a datetime, from the midnight of a date.
        """
        if isinstance(moment, datetime.datetime):
            day = moment.date()
        else:
            day = moment
            moment = datetime.datetime.combine(moment, datetime.time.min)
        cash = self._cash.at(account.pk, day)
        total = cash if cash is not None else account.opening_cash_value.amount
        for holding in self._holdings.get(account.pk, []):
            value = self._history.at(holding.pk, moment)
            if value is not None:
                total += value
            elif holding.initial_valuation_date <= day:
                total += holding.initial_value.amount
        return total
