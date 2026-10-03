"""Figures of the dashboard: net worth, allocation, asset registry and flows.

Every asset of the default currency is valued once, today and 30 days ago;
the hero totals, the allocation strip and the registry all derive from those
rows so they always add up.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from base.services.deadlines import Deadline, upcoming_deadlines
from base.services.ownership import HolderResolver
from base.services.snapshots import month_starts, net_worth_history
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from property.models import Property, PropertyLoan
from property.models.scpi import SCPIInvestment
from property.services.monthly_flows import monthly_flows

#: Days of the short-term change shown everywhere on the dashboard.
CHANGE_DAYS = 30
#: An asset losing more than this percentage over CHANGE_DAYS is flagged.
ALERT_DROP_PCT = Decimal(-5)
#: Deadlines shown in the watch list.
WATCH_DEADLINES = 4


@dataclass(frozen=True)
class AssetClass:
    """A class of assets: its label, chart colour token and page."""

    label: str | Promise
    color: str
    url_name: str


ASSET_CLASSES: dict[str, AssetClass] = {
    "property": AssetClass(_("Properties"), "c1", "property:index"),
    "investment": AssetClass(_("Investments"), "c2", "finance:index"),
    "saving": AssetClass(_("Savings"), "c3", "finance:index"),
    "scpi": AssetClass(_("SCPI"), "c4", "property:scpi_list"),
    "other": AssetClass(_("Other assets"), "c5", "finance:other_asset_list"),
}


def _pct(new: Decimal, old: Decimal) -> Decimal | None:
    """Relative change from *old* to *new* in percent, None without a base."""
    if not old:
        return None
    return (new - old) / abs(old) * 100


@dataclass(frozen=True)
class RegistryRow:
    """One asset of the registry."""

    kind: str
    name: str
    sub: str
    holder: str
    value: Decimal
    old_value: Decimal
    url: str
    #: Gross value (properties only: before the remaining loans).
    gross: Decimal | None = None

    @property
    def change(self) -> Decimal:
        return self.value - self.old_value

    @property
    def change_pct(self) -> Decimal | None:
        return _pct(self.value, self.old_value)


@dataclass
class RegistryGroup:
    """The rows of one asset class, with their totals."""

    kind: str
    rows: list[RegistryRow] = field(default_factory=list)
    net_total: Decimal = Decimal(0)

    @property
    def asset_class(self) -> AssetClass:
        return ASSET_CLASSES[self.kind]

    @property
    def value(self) -> Decimal:
        return sum((r.value for r in self.rows), Decimal(0))

    @property
    def old_value(self) -> Decimal:
        return sum((r.old_value for r in self.rows), Decimal(0))

    @property
    def change_pct(self) -> Decimal | None:
        return _pct(self.value, self.old_value)

    @property
    def share(self) -> Decimal:
        """Part of the net worth, in percent."""
        return self.value / self.net_total * 100 if self.net_total else Decimal(0)


@dataclass(frozen=True)
class Hero:
    """Net worth summary of the hero card."""

    net: Decimal
    gross: Decimal
    debt: Decimal
    change_30d: Decimal
    change_30d_pct: Decimal | None
    change_12m: Decimal | None
    change_12m_pct: Decimal | None

    @property
    def debt_ratio(self) -> Decimal:
        """Remaining loans over the gross assets, in percent."""
        return self.debt / self.gross * 100 if self.gross else Decimal(0)


@dataclass(frozen=True)
class Liability:
    """A loan still being repaid."""

    name: str
    lender: str
    monthly: Decimal
    end_date: datetime.date
    remaining: Decimal
    repaid_pct: Decimal
    url: str


@dataclass(frozen=True)
class PropertyFlow:
    """Median monthly flows of one property."""

    name: str
    url: str
    rents: Decimal
    charges: Decimal
    loan: Decimal
    cashflow: Decimal


@dataclass(frozen=True)
class WatchItem:
    """An asset losing value, or a deadline coming soon."""

    title: str
    target: str
    url: str
    row: RegistryRow | None = None
    deadline: Deadline | None = None


# ── Registry ────────────────────────────────────────────────────────────────


def _account_rows(model, kind, url_name, currency, holders, then):
    accounts = model.objects.active().select_related("account_type")
    for account in accounts:
        if account.currency != currency:
            continue
        yield RegistryRow(
            kind=kind,
            name=str(account),
            sub=" · ".join(
                p for p in (account.account_type.name, account.institution) if p
            ),
            holder=holders.label(account),
            value=account.get_value().amount,
            old_value=account.get_value(max_date=then).amount,
            url=reverse(url_name, kwargs={"pk": account.pk}),
        )


def _property_rows(currency, holders, then):
    properties = (
        Property.objects.filter(is_active=True)
        .prefetch_related("loans__amortization_entries")
        .order_by("name")
    )
    for prop in properties:
        if prop.currency != currency:
            continue
        gross = prop.gross_value.amount
        remaining = prop.total_remaining_loans.amount
        yield RegistryRow(
            kind="property",
            name=prop.name,
            sub=prop.city or prop.get_property_type_display(),  # ty: ignore[unresolved-attribute]
            holder=holders.label(prop),
            value=gross - remaining,
            old_value=prop.net_value_at_date(then.date()).amount,
            url=reverse("property:detail", kwargs={"pk": prop.pk}),
            gross=gross,
        )


def _scpi_rows(currency, holders, today, then):
    by_fund: dict[int, list[SCPIInvestment]] = defaultdict(list)
    investments = SCPIInvestment.objects.filter(sold_date__isnull=True).select_related(
        "scpi"
    )
    for investment in investments:
        if investment.currency == currency:
            by_fund[investment.scpi_id].append(investment)  # ty: ignore[unresolved-attribute]
    for group in sorted(by_fund.values(), key=lambda g: g[0].scpi.name):
        scpi = group[0].scpi
        yield RegistryRow(
            kind="scpi",
            name=scpi.name,
            sub=scpi.management_company,
            holder=holders.label(*group),
            value=sum((i.get_estimated_value(today).amount for i in group), Decimal(0)),
            old_value=sum(
                (i.get_estimated_value(then.date()).amount for i in group), Decimal(0)
            ),
            url=reverse("property:scpi_fund_detail", kwargs={"scpi_pk": scpi.pk}),
        )


def _other_rows(currency, holders, today, then):
    for asset in OtherAsset.objects.filter(is_active=True):
        if asset.currency != currency:
            continue
        yield RegistryRow(
            kind="other",
            name=asset.name,
            sub=asset.get_category_display(),  # ty: ignore[unresolved-attribute]
            holder=holders.label(asset),
            value=asset.get_value(today).amount,
            old_value=asset.get_value(then.date()).amount,
            url=reverse("finance:other_asset_detail", kwargs={"pk": asset.pk}),
        )


def registry(currency: str, today: datetime.date) -> list[RegistryGroup]:
    """Every held asset of *currency*, grouped by class (empty classes left out)."""
    then = datetime.datetime.combine(
        today - datetime.timedelta(days=CHANGE_DAYS), datetime.time()
    )
    holders = HolderResolver()
    rows = [
        *_property_rows(currency, holders, then),
        *_account_rows(
            InvestmentAccount,
            "investment",
            "finance:investment_detail",
            currency,
            holders,
            then,
        ),
        *_account_rows(
            SavingAccount, "saving", "finance:saving_detail", currency, holders, then
        ),
        *_scpi_rows(currency, holders, today, then),
        *_other_rows(currency, holders, today, then),
    ]
    net = sum((r.value for r in rows), Decimal(0))
    groups = {kind: RegistryGroup(kind=kind, net_total=net) for kind in ASSET_CLASSES}
    for row in rows:
        groups[row.kind].rows.append(row)
    for group in groups.values():
        group.rows.sort(key=lambda r: r.value, reverse=True)
    return [g for g in groups.values() if g.rows]


# ── Summary, liabilities and flows ──────────────────────────────────────────


def _history_net(values: dict[str, Decimal]) -> Decimal:
    return (
        values["savings"]
        + values["investments"]
        + values["properties_net"]
        + values["scpi"]
        + values["other"]
    )


def hero_summary(
    groups: list[RegistryGroup], currency: str, today: datetime.date
) -> Hero:
    """Net and gross worth, debts and their changes over 30 days and 12 months."""
    rows = [r for g in groups for r in g.rows]
    net = sum((r.value for r in rows), Decimal(0))
    old = sum((r.old_value for r in rows), Decimal(0))
    debt = sum((r.gross - r.value for r in rows if r.gross is not None), Decimal(0))
    year_ago = net_worth_history(month_starts(12, today)[:1], currency, today)[0]
    net_year_ago = _history_net(year_ago)
    return Hero(
        net=net,
        gross=net + debt,
        debt=debt,
        change_30d=net - old,
        change_30d_pct=_pct(net, old),
        change_12m=net - net_year_ago if net_year_ago else None,
        change_12m_pct=_pct(net, net_year_ago),
    )


def liabilities(today: datetime.date) -> list[Liability]:
    """Loans of the active properties not fully repaid, largest balance first."""
    result = []
    loans = (
        PropertyLoan.objects.filter(property__is_active=True)
        .select_related("property")
        .prefetch_related("amortization_entries")
    )
    for loan in loans:
        remaining = loan.remaining_balance(today).amount
        if remaining <= 0:
            continue
        original = loan.original_amount.amount
        monthly = (loan.monthly_payment.amount if loan.monthly_payment else 0) + (
            loan.insurance.amount if loan.insurance else 0
        )
        result.append(
            Liability(
                name=loan.property.name,
                lender=loan.lender or loan.name or "",
                monthly=Decimal(monthly),
                end_date=loan.end_date,
                remaining=remaining,
                repaid_pct=(original - remaining) / original * 100
                if original
                else Decimal(0),
                url=reverse("property:detail", kwargs={"pk": loan.property_id}),  # ty: ignore[unresolved-attribute]
            )
        )
    result.sort(key=lambda loan: loan.remaining, reverse=True)
    return result


def property_flows(today: datetime.date) -> list[PropertyFlow]:
    """Median monthly flows of every active property."""
    result = []
    for prop in Property.objects.filter(is_active=True).order_by("name"):
        flows = monthly_flows(prop, today)
        result.append(
            PropertyFlow(
                name=prop.name,
                url=reverse("property:detail", kwargs={"pk": prop.pk}),
                rents=flows.rents,
                charges=flows.charges,
                loan=flows.loan,
                cashflow=flows.cashflow,
            )
        )
    return result


def watch_items(groups: list[RegistryGroup], today: datetime.date) -> list[WatchItem]:
    """Assets that dropped over CHANGE_DAYS, then the deadlines coming soon."""
    drops = sorted(
        (
            r
            for g in groups
            for r in g.rows
            if r.change_pct is not None and r.change_pct <= ALERT_DROP_PCT
        ),
        key=lambda r: r.change_pct or 0,
    )
    items = [WatchItem(title=r.name, target="", url=r.url, row=r) for r in drops]
    soon = [d for d in upcoming_deadlines(today) if d.days_left >= 0]
    items += [
        WatchItem(title=str(d.detail), target=d.title, url=d.url, deadline=d)
        for d in soon[:WATCH_DEADLINES]
    ]
    return items


def default_currency() -> str:
    """Currency of the first account or property, else the configured default."""
    for model in (InvestmentAccount, SavingAccount):
        account = model.objects.active().first()
        if account is not None:
            return account.currency
    prop = Property.objects.filter(is_active=True).first()
    return prop.currency if prop is not None else settings.DEFAULT_CURRENCY
