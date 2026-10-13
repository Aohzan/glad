"""Property and SCPI flows of a calendar year, for the budget.

The figures are read from the property ledger (recurring entries expanded,
future years included), the loan schedules and the SCPI dividends and
subscriptions; nothing is copied into the budget.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Prefetch, Q

from base.services.ownership import HolderResolver
from budget.services.perspective import Perspective
from property.models import Property, PropertyLedgerEntry
from property.models.ledger import ManagementCategory
from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment
from property.services.cashflow import ledger_totals_by_category
from property.services.loans import loan_costs_between
from property.utils import LoanCosts

#: Ledger categories left out of the budget: security deposits are owed back
#: to the tenant, they are neither income nor expenses.
EXCLUDED_CATEGORIES = frozenset(
    {ManagementCategory.DEPOSIT_IN.value, ManagementCategory.DEPOSIT_OUT.value}
)


def year_bounds(year: int) -> tuple[datetime.date, datetime.date]:
    """First and last day of *year*."""
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


@dataclass(frozen=True)
class PropertyFlows:
    """Flows of one property over a year, for the part of the perspective."""

    property: Property
    #: Ledger income by management category.
    income: dict[str, Decimal] = field(default_factory=dict)
    #: Ledger expenses by management category.
    expenses: dict[str, Decimal] = field(default_factory=dict)
    loan: LoanCosts = field(default_factory=LoanCosts)

    @property
    def rent(self) -> Decimal:
        """Rent collected (the income banks count at 70 % in the debt ratio)."""
        return self.income.get(ManagementCategory.RENT_COLLECTED.value, Decimal(0))

    @property
    def is_empty(self) -> bool:
        """True when the property has no flow in the year."""
        return not (
            any(self.income.values()) or any(self.expenses.values()) or self.loan.total
        )


def _scaled(amounts: dict[str, Decimal], ratio: Decimal) -> dict[str, Decimal]:
    return {
        cat: amount * ratio
        for cat, amount in amounts.items()
        if cat not in EXCLUDED_CATEGORIES and amount * ratio
    }


def _scaled_costs(costs: LoanCosts, ratio: Decimal) -> LoanCosts:
    return LoanCosts(
        principal=costs.principal * ratio,
        interest=costs.interest * ratio,
        insurance=costs.insurance * ratio,
    )


def property_year_flows(
    year: int,
    perspective: Perspective,
    *,
    currency: str,
    excluded: set[int] | None = None,
    resolver: HolderResolver | None = None,
) -> list[PropertyFlows]:
    """Flows of the properties held during *year*, except the *excluded* ones.

    Rents and running costs follow the usufructuary's side of a dismembered
    property and loan installments the bare owner's (see
    :meth:`Perspective.asset_ratio`). Properties in another currency than
    *currency* are left out.
    """
    first, last = year_bounds(year)
    resolver = resolver or HolderResolver()
    properties = (
        Property.objects.filter(buying_date__lte=last)
        .filter(Q(selling_date__isnull=True) | Q(selling_date__gte=first))
        .exclude(pk__in=excluded or ())
        .prefetch_related(
            Prefetch(
                "ledger_entries",
                queryset=PropertyLedgerEntry.objects.prefetch_related("exceptions"),
            ),
            "loans__amortization_entries",
        )
        .order_by("name")
    )
    flows = []
    for prop in properties:
        if str(prop.currency) != currency:
            continue
        rows = resolver.rows(prop)
        ratio = perspective.asset_ratio(rows)
        capital_ratio = perspective.asset_ratio(rows, capital=True)
        if not ratio and not capital_ratio:
            continue
        ledger = ledger_totals_by_category(prop, first, last)
        item = PropertyFlows(
            property=prop,
            income=_scaled(ledger.income, ratio),
            expenses=_scaled(ledger.expenses, ratio),
            loan=_scaled_costs(
                loan_costs_between(prop.loans.all(), first, last), capital_ratio
            ),
        )
        if not item.is_empty:
            flows.append(item)
    return flows


@dataclass(frozen=True)
class SCPIFlows:
    """Dividends received and shares subscribed in one SCPI fund over a year."""

    scpi: SCPI
    dividends: Decimal = Decimal(0)
    subscriptions: Decimal = Decimal(0)


def _held_in_year(investment: SCPIInvestment, first, last) -> bool:
    return investment.subscription_date <= last and (
        investment.sold_date is None or investment.sold_date >= first
    )


def scpi_year_flows(
    year: int,
    perspective: Perspective,
    *,
    currency: str,
    resolver: HolderResolver | None = None,
) -> list[SCPIFlows]:
    """Net dividends and subscriptions of the SCPI funds during *year*.

    The dividends are recorded for the whole fund: they are split between
    the investments that receive them (full ownership or usufruct) by number
    of shares, each investment counting for the part of the perspective.
    """
    first, last = year_bounds(year)
    resolver = resolver or HolderResolver()
    funds = SCPI.objects.prefetch_related(
        Prefetch(
            "dividends",
            queryset=SCPIDividend.objects.filter(payment_date__range=(first, last)),
        ),
        "investments",
    ).order_by("name")
    flows = []
    for fund in funds:
        investments = [
            i for i in fund.investments.all() if _held_in_year(i, first, last)
        ]
        dividends = sum(
            (
                d.net_amount.amount
                for d in fund.dividends.all()
                if str(d.net_amount.currency) == currency
            ),
            Decimal(0),
        )
        if dividends:
            receiving = [
                i
                for i in investments
                if i.ownership_type != SCPIInvestment.OwnershipType.BARE
            ]
            shares = sum((i.shares_count for i in receiving), Decimal(0))
            if shares:
                dividends *= (
                    sum(
                        (
                            i.shares_count * perspective.asset_ratio(resolver.rows(i))
                            for i in receiving
                        ),
                        Decimal(0),
                    )
                    / shares
                )
            else:
                dividends *= perspective.shared_ratio
        subscriptions = sum(
            (
                i.shares_count
                * i.unit_purchase_price.amount
                * perspective.asset_ratio(resolver.rows(i), capital=True)
                for i in investments
                if first <= i.subscription_date <= last
                and str(i.unit_purchase_price.currency) == currency
            ),
            Decimal(0),
        )
        if dividends or subscriptions:
            flows.append(
                SCPIFlows(scpi=fund, dividends=dividends, subscriptions=subscriptions)
            )
    return flows
