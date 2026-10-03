"""Monthly net worth history, stored as snapshots for the past months.

Computing the value of every asset at every month start is slow, and the past
rarely changes: past months are stored in ``NetWorthSnapshot`` the first time
they are needed, the current month is always computed live. Any change to a
value, an account or an asset deletes the snapshots it may affect (see
``base.signals``), so the history stays exact.
"""

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from base.models import NetWorthSnapshot
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from property.models import Property
from property.models.scpi import SCPIInvestment

logger = logging.getLogger(__name__)

SERIES = (
    "savings",
    "investments",
    "properties_net",
    "properties_gross",
    "scpi",
    "other",
)


@dataclass(frozen=True)
class _Assets:
    """Every asset of one currency, loaded once for all the months."""

    saving_accounts: list[SavingAccount]
    investment_accounts: list[InvestmentAccount]
    properties: list[Property]
    scpi_investments: list[SCPIInvestment]
    other_assets: list[OtherAsset]


def _load_assets(currency: str) -> _Assets:
    return _Assets(
        saving_accounts=[
            a for a in SavingAccount.objects.all() if a.currency == currency
        ],
        investment_accounts=[
            a for a in InvestmentAccount.objects.all() if a.currency == currency
        ],
        # The loans are read once and their schedules kept for every month.
        properties=[
            p
            for p in Property.objects.filter(is_active=True).prefetch_related(
                "loans__amortization_entries"
            )
            if p.currency == currency
        ],
        scpi_investments=[
            i
            for i in SCPIInvestment.objects.select_related("scpi")
            if i.currency == currency
        ],
        other_assets=[a for a in OtherAsset.objects.all() if a.currency == currency],
    )


def _is_held(account, month: datetime.date) -> bool:
    """Active accounts, and closed ones until their closing date."""
    return account.is_active or bool(
        account.closing_date and account.closing_date > month
    )


def _amount(obj, compute) -> Decimal:
    """``compute(obj).amount``, zero (and logged) when it cannot be computed."""
    try:
        return compute(obj).amount
    except Exception:
        logger.warning("Cannot value %s", obj, exc_info=True)
        return Decimal(0)


def _account_value(account, at: datetime.datetime):
    """Account value at *at*, retried with a date for date-only lookups."""
    try:
        return account.get_value(max_date=at)
    except TypeError:
        return account.get_value(max_date=at.date())


def compute_month(assets: _Assets, month: datetime.date) -> dict[str, Decimal]:
    """Value of every series at the start of *month*.

    An asset that cannot be valued counts as zero rather than breaking the
    whole history.
    """
    at = datetime.datetime.combine(month, datetime.time())
    values = dict.fromkeys(SERIES, Decimal(0))
    for account in assets.saving_accounts:
        if _is_held(account, month):
            values["savings"] += _amount(account, lambda a: _account_value(a, at))
    for account in assets.investment_accounts:
        if _is_held(account, month):
            values["investments"] += _amount(account, lambda a: _account_value(a, at))
    for prop in assets.properties:
        if prop.buying_date <= month:
            values["properties_net"] += _amount(
                prop, lambda p: p.net_value_at_date(month)
            )
            values["properties_gross"] += _amount(
                prop, lambda p: p.get_value(max_date=at)
            )
    for investment in assets.scpi_investments:
        values["scpi"] += _amount(investment, lambda i: i.get_estimated_value(month))
    for asset in assets.other_assets:
        values["other"] += _amount(asset, lambda a: a.get_value(month))
    return values


def month_starts(count: int, today: datetime.date | None = None) -> list[datetime.date]:
    """The first day of the last *count* months and of the current one, oldest first."""
    current = (today or datetime.date.today()).replace(day=1)
    return [current - relativedelta(months=i) for i in range(count, -1, -1)]


def net_worth_history(
    months: list[datetime.date],
    currency: str,
    today: datetime.date | None = None,
) -> list[dict[str, Decimal]]:
    """Series values for each of *months*, from the snapshots when available.

    Missing past months are computed and stored; the current month (and any
    later one) is computed without being stored.
    """
    current = (today or datetime.date.today()).replace(day=1)
    stored = {
        s.month: s
        for s in NetWorthSnapshot.objects.filter(currency=currency, month__in=months)
    }
    assets: _Assets | None = None
    result = []
    for month in months:
        snapshot = stored.get(month)
        if snapshot is not None:
            result.append({name: getattr(snapshot, name) for name in SERIES})
            continue
        if assets is None:
            assets = _load_assets(currency)
        values = compute_month(assets, month)
        if month < current:
            NetWorthSnapshot.objects.update_or_create(
                month=month, currency=currency, defaults=values
            )
        result.append(values)
    return result


def invalidate_from(day: datetime.date | datetime.datetime | None) -> None:
    """Delete the snapshots that a change dated *day* may affect (all when None)."""
    snapshots = NetWorthSnapshot.objects.all()
    if day is not None:
        if isinstance(day, datetime.datetime):
            day = day.date()
        # A value dated on a month start already counts in that month.
        snapshots = snapshots.filter(month__gte=day)
    snapshots.delete()
