"""Unified history of the dated operations recorded on every asset.

Operations are the value updates, deposits and dividends stored for the
accounts, holdings, other assets, properties and SCPI. They are read with one
SQL ``UNION`` so the history can be ordered and paginated in the database.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import CharField, F, Model, QuerySet, Value
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from property.models import Property, PropertyValue
from property.models.scpi import SCPI, SCPIDividend


@dataclass(frozen=True)
class OperationKind:
    """How one source table is read and shown."""

    model: type[Model]
    date_field: str
    amount_field: str
    target_field: str
    label: str | Promise
    icon: str
    #: ``value`` for a valuation, ``in``/``out`` for a cash movement.
    flow: str
    #: Whether the date column is a ``DateTimeField``.
    timestamp: bool = False


OPERATION_KINDS: dict[str, OperationKind] = {
    "saving_value": OperationKind(
        SavingAccountValue,
        "value_date",
        "value",
        "account_id",
        _("Value update"),
        "refresh-cw",
        "value",
        timestamp=True,
    ),
    "saving_deposit": OperationKind(
        SavingAccountDeposit,
        "deposit_date",
        "amount",
        "account_id",
        _("Deposit"),
        "arrow-down-left",
        "in",
        timestamp=True,
    ),
    "investment_cash": OperationKind(
        InvestmentAccountCash,
        "value_date",
        "value",
        "account_id",
        _("Cash update"),
        "refresh-cw",
        "value",
    ),
    "investment_deposit": OperationKind(
        InvestmentAccountDeposit,
        "deposit_date",
        "amount",
        "account_id",
        _("Deposit"),
        "arrow-down-left",
        "in",
    ),
    "holding_value": OperationKind(
        InvestmentAccountHoldingHistory,
        "valuation_date",
        "value",
        "holding_id",
        _("Holding valuation"),
        "chart-line",
        "value",
        timestamp=True,
    ),
    "other_asset_value": OperationKind(
        OtherAssetValue,
        "value_date",
        "value",
        "asset_id",
        _("Value update"),
        "refresh-cw",
        "value",
    ),
    "property_value": OperationKind(
        PropertyValue,
        "valuation_date",
        "value",
        "property_id",
        _("Property valuation"),
        "house",
        "value",
    ),
    "scpi_dividend": OperationKind(
        SCPIDividend,
        "payment_date",
        "net_amount",
        "scpi_id",
        _("Dividend"),
        "coins",
        "in",
    ),
}


@dataclass(frozen=True)
class Operation:
    """One dated operation, resolved for display."""

    kind: str
    date: datetime.date
    amount: Money
    target: str
    url: str

    @property
    def label(self) -> str | Promise:
        return OPERATION_KINDS[self.kind].label

    @property
    def icon(self) -> str:
        return OPERATION_KINDS[self.kind].icon

    @property
    def flow(self) -> str:
        return OPERATION_KINDS[self.kind].flow


def _source(kind: str, spec: OperationKind) -> QuerySet:
    date = TruncDate(spec.date_field) if spec.timestamp else F(spec.date_field)
    # Every column is an annotation, so all the queries of the UNION select
    # the same columns in the same order.
    # The model orderings are cleared: a UNION member cannot be ordered.
    return (
        spec.model.objects.order_by()
        .annotate(
            g_kind=Value(kind, output_field=CharField()),
            g_date=date,
            g_id=F("pk"),
            g_amount=F(spec.amount_field),
            g_currency=F(f"{spec.amount_field}_currency"),
            g_target=F(spec.target_field),
        )
        .values("g_kind", "g_date", "g_id", "g_amount", "g_currency", "g_target")
    )


def operations_queryset(kinds: list[str] | None = None) -> QuerySet:
    """Operations of *kinds* (all by default), most recent first."""
    selected = [k for k in (kinds or OPERATION_KINDS) if k in OPERATION_KINDS]
    if not selected:
        selected = list(OPERATION_KINDS)
    queries = [_source(kind, OPERATION_KINDS[kind]) for kind in selected]
    union = queries[0].union(*queries[1:], all=True) if len(queries) > 1 else queries[0]
    return union.order_by("-g_date", "-g_id")


def _targets(rows) -> dict[tuple[str, int], tuple[str, str]]:
    """Name and URL of the asset behind each ``(kind, target_id)``."""
    wanted: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        wanted[row["g_kind"]].add(row["g_target"])

    def ids(*kinds: str) -> set[int]:
        return set().union(*(wanted.get(k, set()) for k in kinds))

    resolved: dict[tuple[str, int], tuple[str, str]] = {}

    def add(kinds, objects, url, name=str):
        for obj in objects:
            entry = (name(obj), url(obj))
            for kind in kinds:
                resolved[(kind, obj.pk)] = entry

    def detail(url_name: str, kwarg: str = "pk"):
        return lambda obj: reverse(url_name, kwargs={kwarg: obj.pk})

    saving = ("saving_value", "saving_deposit")
    add(
        saving,
        SavingAccount.objects.filter(pk__in=ids(*saving)).select_related(
            "account_type"
        ),
        detail("finance:saving_detail"),
    )
    investment = ("investment_cash", "investment_deposit")
    add(
        investment,
        InvestmentAccount.objects.filter(pk__in=ids(*investment)).select_related(
            "account_type"
        ),
        detail("finance:investment_detail"),
    )
    add(
        ("holding_value",),
        InvestmentAccountHolding.objects.filter(pk__in=ids("holding_value")),
        lambda h: reverse(
            "finance:holding_detail",
            kwargs={"account_pk": h.account_id, "holding_pk": h.pk},
        ),
        name=lambda h: h.name or h.code or "",
    )
    add(
        ("other_asset_value",),
        OtherAsset.objects.filter(pk__in=ids("other_asset_value")),
        detail("finance:other_asset_detail"),
    )
    add(
        ("property_value",),
        Property.objects.filter(pk__in=ids("property_value")),
        detail("property:detail"),
        name=lambda p: p.name,
    )
    add(
        ("scpi_dividend",),
        SCPI.objects.filter(pk__in=ids("scpi_dividend")),
        detail("property:scpi_fund_detail", "scpi_pk"),
        name=lambda s: s.name,
    )
    return resolved


def resolve(rows) -> list[Operation]:
    """Turn rows of :func:`operations_queryset` into :class:`Operation`."""
    rows = list(rows)
    targets = _targets(rows)
    operations = []
    for row in rows:
        target, url = targets.get((row["g_kind"], row["g_target"]), ("", ""))
        operations.append(
            Operation(
                kind=row["g_kind"],
                date=row["g_date"],
                amount=Money(Decimal(row["g_amount"]), row["g_currency"]),
                target=target,
                url=url,
            )
        )
    return operations


def recent_operations(limit: int = 5) -> list[Operation]:
    """The *limit* most recent operations."""
    return resolve(operations_queryset()[:limit])
