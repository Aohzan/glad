"""Breakdown of the net worth by asset class and by liquidity.

Every asset contributes its current value in the reference currency (assets in
other currencies are left out, like on the dashboard):

- saving accounts: cash, with the liquidity of their envelope;
- investment accounts: their cash, and each holding with its asset class, both
  with the liquidity of the envelope;
- properties (net of loans) and SCPI: real estate, illiquid;
- other assets: the asset class and liquidity of their category.

Each asset counts for the part held by the chosen household members, or by
the whole household (see :func:`base.services.ownership.held_ratio`).
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils.translation import gettext

from base.choices import AssetClass, Liquidity
from base.models import household_members
from base.services.ownership import HolderResolver, held_ratio
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from property.models import Property
from property.models.scpi import SCPIInvestment

#: Label of the holdings whose asset class is not set.
UNCLASSIFIED = ""
#: Recommended size of the emergency fund, in months of expenses.
EMERGENCY_FUND_MONTHS = (3, 6)


@dataclass(frozen=True)
class AllocationItem:
    """One asset (or part of an account) in the breakdown."""

    label: str
    amount: Decimal
    asset_class: str
    liquidity: str


@dataclass(frozen=True)
class AllocationRow:
    """Total of one asset class or liquidity level."""

    key: str
    label: str
    amount: Decimal
    percent: float


@dataclass
class Allocation:
    """Breakdown of the assets of one currency."""

    currency: str
    items: list[AllocationItem] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        """Sum of the positive items."""
        return sum((i.amount for i in self.items if i.amount > 0), Decimal(0))

    def _rows(self, attr: str, labels: dict[str, str]) -> list[AllocationRow]:
        totals: dict[str, Decimal] = {}
        for item in self.items:
            if item.amount > 0:
                key = getattr(item, attr)
                totals[key] = totals.get(key, Decimal(0)) + item.amount
        total = self.total
        rows = [
            AllocationRow(
                key=key,
                label=labels.get(key, str(key)),
                amount=amount,
                percent=float(amount / total * 100) if total else 0.0,
            )
            for key, amount in totals.items()
        ]
        return sorted(rows, key=lambda r: r.amount, reverse=True)

    def by_asset_class(self) -> list[AllocationRow]:
        """Totals per asset class, largest first."""
        labels = {str(k): str(v) for k, v in AssetClass.choices}
        labels[UNCLASSIFIED] = gettext("Not classified")
        return self._rows("asset_class", labels)

    def by_liquidity(self) -> list[AllocationRow]:
        """Totals per liquidity level, largest first."""
        return self._rows("liquidity", {str(k): str(v) for k, v in Liquidity.choices})

    def amount_for_liquidity(self, liquidity: str) -> Decimal:
        """Total of the items of one liquidity level."""
        return sum(
            (i.amount for i in self.items if i.liquidity == liquidity and i.amount > 0),
            Decimal(0),
        )


class _Shares:
    """Part of each asset held by some household members, or by all of them."""

    def __init__(self, people: set[int] | None):
        self.household = people is None
        self.people = (
            set(household_members().values_list("pk", flat=True))
            if people is None
            else people
        )
        self.holders = HolderResolver()
        self.today = datetime.date.today()

    def ratio(self, obj) -> Decimal:
        """Part of the value of *obj* held by the members."""
        return held_ratio(
            self.holders.rows(obj), self.people, self.today, household=self.household
        )


def _investment_items(currency: str, shares: _Shares):
    holdings = InvestmentAccountHolding.objects.filter(is_active=True)
    by_account: dict[int, list[InvestmentAccountHolding]] = {}
    for holding in holdings:
        by_account.setdefault(holding.account_id, []).append(holding)  # ty: ignore[unresolved-attribute]
    accounts = InvestmentAccount.objects.active().select_related("account_type")
    for account in accounts:
        ratio = shares.ratio(account)
        if account.currency != currency or not ratio:
            continue
        liquidity = account.liquidity
        yield AllocationItem(
            label=f"{account} — {gettext('Cash')}",
            amount=account.current_cash_value.amount * ratio,
            asset_class=AssetClass.CASH,
            liquidity=liquidity,
        )
        for holding in by_account.get(account.pk, []):
            yield AllocationItem(
                label=f"{account} — {holding.short_name}",
                amount=holding.value.amount * ratio,
                asset_class=holding.asset_class or UNCLASSIFIED,
                liquidity=liquidity,
            )


def compute_allocation(currency: str, people: set[int] | None = None) -> Allocation:
    """Breakdown of the current assets held in *currency*.

    Each asset counts for the part held by the users *people* (primary keys),
    or by the whole household when None.
    """
    allocation = Allocation(currency=currency)
    items = allocation.items
    shares = _Shares(people)
    for account in SavingAccount.objects.active().select_related("account_type"):
        ratio = shares.ratio(account)
        if account.currency == currency and ratio:
            items.append(
                AllocationItem(
                    label=str(account),
                    amount=account.current_value.amount * ratio,
                    asset_class=AssetClass.CASH,
                    liquidity=account.liquidity,
                )
            )
    items.extend(_investment_items(currency, shares))
    for prop in Property.objects.filter(is_active=True):
        ratio = shares.ratio(prop)
        if prop.currency == currency and ratio:
            items.append(
                AllocationItem(
                    label=str(prop),
                    amount=prop.net_value.amount * ratio,
                    asset_class=AssetClass.REAL_ESTATE,
                    liquidity=Liquidity.ILLIQUID,
                )
            )
    for investment in SCPIInvestment.objects.select_related("scpi"):
        ratio = shares.ratio(investment)
        if investment.currency == currency and ratio:
            items.append(
                AllocationItem(
                    label=str(investment.scpi),
                    amount=investment.get_estimated_value(shares.today).amount * ratio,
                    asset_class=AssetClass.REAL_ESTATE,
                    liquidity=Liquidity.ILLIQUID,
                )
            )
    for asset in OtherAsset.objects.filter(is_active=True):
        ratio = shares.ratio(asset)
        if asset.currency == currency and ratio:
            items.append(
                AllocationItem(
                    label=str(asset),
                    amount=asset.current_value.amount * ratio,
                    asset_class=asset.asset_class,
                    liquidity=asset.effective_liquidity,
                )
            )
    return allocation


@dataclass(frozen=True)
class EmergencyFund:
    """Immediately available savings measured in months of expenses."""

    available: Decimal
    monthly_expenses: Decimal | None

    @property
    def months(self) -> float | None:
        """Months of expenses covered, None without expenses."""
        if not self.monthly_expenses:
            return None
        return float(self.available / self.monthly_expenses)

    @property
    def level(self) -> str | None:
        """``danger`` below the minimum, ``success`` within the range, ``info`` above."""
        months = self.months
        if months is None:
            return None
        low, high = EMERGENCY_FUND_MONTHS
        if months < low:
            return "danger"
        return "success" if months <= high else "info"

    @property
    def target_range(self) -> tuple[Decimal, Decimal] | None:
        """Recommended amount range, None without expenses."""
        if not self.monthly_expenses:
            return None
        low, high = EMERGENCY_FUND_MONTHS
        return self.monthly_expenses * low, self.monthly_expenses * high


def emergency_fund(
    allocation: Allocation, monthly_expenses: Decimal | None
) -> EmergencyFund:
    """Emergency fund status from the immediately available assets."""
    return EmergencyFund(
        available=allocation.amount_for_liquidity(Liquidity.IMMEDIATE),
        monthly_expenses=monthly_expenses,
    )
