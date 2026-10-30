"""Household-wide tools: net worth, allocation, deadlines and pending checks."""

import datetime

from base.services import dashboard
from base.services.allocation import UNCLASSIFIED, AllocationRow, compute_allocation
from base.services.deadlines import upcoming_deadlines
from base.services.ownership import net_worth_by_person
from base.services.snapshots import month_starts, net_worth_history
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from mcp_server.serializers import decimal, percent, ref, to_json
from mcp_server.server import glad_tool
from property.models import Property, SCPIInvestment
from property.services.checks import PendingOccurrence, pending_occurrences
from rental.services.dashboard import lease_rows
from rental.services.payments import arrears


def _currencies() -> set[str]:
    """Currencies of the assets currently held."""
    return {
        *(a.currency for a in SavingAccount.objects.active()),
        *(a.currency for a in InvestmentAccount.objects.active()),
        *(a.currency for a in OtherAsset.objects.filter(is_active=True)),
        *(p.currency for p in Property.objects.filter(is_active=True)),
        *(i.currency for i in SCPIInvestment.objects.filter(sold_date__isnull=True)),
    }


def _left_out(currency: str, today: datetime.date) -> list[dict]:
    """The assets held in another currency than *currency*, not converted."""
    return [
        {
            "kind": row.kind,
            "name": row.name,
            "holder": row.holder,
            "value": {"amount": decimal(row.value), "currency": other},
        }
        for other in sorted(_currencies() - {currency})
        for group in dashboard.registry(other, today)
        for row in group.rows
    ]


@glad_tool()
def get_net_worth(currency: str | None = None) -> dict:
    """Net worth of the household: totals, changes over 30 days and 12 months,
    every asset grouped by class with the total and share of each class, the
    remaining loans, and the share of each household member. *currency*
    defaults to the main currency of the data; the assets in another currency
    are not converted: they are listed apart in left_out_other_currencies."""
    today = datetime.date.today()
    currency = currency or dashboard.default_currency()
    groups = dashboard.registry(currency, today)
    hero = dashboard.hero_summary(groups, currency, today)
    people, unassigned, outside = net_worth_by_person(currency, today)
    return {
        "currency": currency,
        "summary": {**to_json(hero), "debt_ratio_pct": decimal(hero.debt_ratio)},
        "asset_classes": [
            {
                "kind": group.kind,
                "label": str(group.asset_class.label),
                "total": decimal(group.value),
                "share_pct": percent(group.share),
                "assets": [
                    {
                        "name": row.name,
                        "detail": row.sub,
                        "holder": row.holder,
                        "value": decimal(row.value),
                        "gross_value": to_json(row.gross),
                        "change_30d": decimal(row.change),
                    }
                    for row in group.rows
                ],
            }
            for group in groups
        ],
        "loans": to_json(dashboard.liabilities(today)),
        "by_person": [
            {
                "person": worth.label,
                "is_child": worth.is_child,
                "total": decimal(worth.total),
                "by_kind": to_json(worth.by_kind),
                "unvalued": worth.unvalued,
            }
            for worth in [*people, unassigned, outside]
            if worth.by_kind or worth.unvalued
        ],
        "left_out_other_currencies": _left_out(currency, today),
    }


@glad_tool()
def get_net_worth_history(months: int = 24, currency: str | None = None) -> dict:
    """Monthly net worth over the last *months* months (at most 240), split by
    asset class, the last point being today."""
    today = datetime.date.today()
    currency = currency or dashboard.default_currency()
    months = max(1, min(months, 240))
    days = [*month_starts(months, today)[:-1], today]
    history = net_worth_history(days, currency, today)
    return {
        "currency": currency,
        "points": [
            {"date": day.isoformat(), **to_json(values)}
            for day, values in zip(days, history, strict=True)
        ],
    }


def _rows(rows: list[AllocationRow]) -> list[dict]:
    return [
        {
            "key": "unclassified" if row.key == UNCLASSIFIED else row.key,
            "label": row.label,
            "amount": decimal(row.amount),
            "share_pct": percent(row.percent),
        }
        for row in rows
    ]


@glad_tool()
def get_allocation(currency: str | None = None) -> dict:
    """Breakdown of the current assets by asset class and by liquidity, as
    the allocation page shows it: the assets worth less than nothing (a
    property whose loans exceed its value) are left out of the total, and
    summed in negative_total; total plus negative_total is the net worth."""
    allocation = compute_allocation(currency or dashboard.default_currency())
    return {
        "currency": allocation.currency,
        "total": decimal(allocation.total),
        "negative_total": decimal(allocation.negative_total),
        "by_asset_class": _rows(allocation.by_asset_class()),
        "by_liquidity": _rows(allocation.by_liquidity()),
    }


@glad_tool()
def get_upcoming_deadlines(limit: int = 50) -> list[dict]:
    """Recent and upcoming deadlines (loan ends, rent revisions, lease ends,
    notices, energy rating bans, account milestones…), soonest first."""
    return [
        {
            "date": deadline.date.isoformat(),
            "days_left": deadline.days_left,
            "kind": deadline.kind,
            "title": deadline.title,
            "detail": str(deadline.detail),
        }
        for deadline in upcoming_deadlines(limit=max(1, min(limit, 200)))
    ]


def _unchecked_by_entry(today: datetime.date) -> list[dict]:
    """The unchecked occurrences grouped by ledger entry, oldest first."""
    by_entry: dict[int, list[PendingOccurrence]] = {}
    for pending in pending_occurrences(up_to=today):
        by_entry.setdefault(pending.entry.pk, []).append(pending)
    return [
        {
            "entry_id": entry.pk,
            "property": ref(entry.property),
            "label": entry.display_label,
            "flow_type": entry.flow_type,
            "count": len(occurrences),
            "oldest_date": occurrences[0].planned_date.isoformat(),
            "latest_date": occurrences[-1].planned_date.isoformat(),
            "total": to_json(
                sum(
                    (o.planned_amount for o in occurrences[1:]),
                    occurrences[0].planned_amount,
                )
            ),
        }
        for occurrences in by_entry.values()
        for entry in [occurrences[0].entry]
    ]


@glad_tool()
def get_pending_checks() -> dict:
    """What needs attention: past occurrences of recurring ledger entries not
    checked yet (rents not marked as received, expenses not confirmed),
    grouped by entry; rent arrears and the issues of the lease checklists."""
    today = datetime.date.today()
    leases = []
    for row in lease_rows(today):
        owed = arrears(row.periods)
        if row.issues or owed:
            leases.append(
                {
                    "lease": ref(row.lease),
                    "property": ref(row.lease.property),
                    "arrears": decimal(owed),
                    "issues": to_json(row.issues),
                }
            )
    return {"unchecked_entries": _unchecked_by_entry(today), "leases": leases}
