"""Savings accounts, investment accounts and other assets."""

import datetime
from typing import Literal

from django.db.models import Max

from base.choices import AssetClass
from base.services.ownership import HolderResolver
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from finance.services.performance import MIN_DAYS, account_performance
from mcp_server.serializers import decimal, money, percent, quantity, ref, to_json
from mcp_server.server import glad_tool

AccountKind = Literal["saving", "investment", "other"]

MODELS = {"saving": SavingAccount, "investment": InvestmentAccount, "other": OtherAsset}


def _last_value_date(account) -> datetime.date | None:
    """Date of the latest value entered for *account*."""
    if isinstance(account, InvestmentAccount):
        dates = [
            account.cash_values.aggregate(last=Max("value_date"))["last"],
            InvestmentAccountHoldingHistory.objects.filter(
                holding__account=account
            ).aggregate(last=Max("valuation_date"))["last"],
        ]
    else:
        dates = [account.values.aggregate(last=Max("value_date"))["last"]]
    days = [d.date() if isinstance(d, datetime.datetime) else d for d in dates if d]
    return max(days, default=None)


def _invested(account) -> bool:
    """True when the account has an opening value or a deposit, the outflows
    an XIRR needs."""
    return bool(account.opening_amount.amount) or (
        account.deposits.filter(amount__gt=0).exists()
    )


def _performance(account) -> dict:
    """XIRR in percent, with the reason when it cannot be computed."""
    performance = account_performance(account)
    row = {
        "xirr_pct": percent(performance.xirr_percent),
        "real_xirr_pct": percent(performance.real_xirr_percent),
    }
    if performance.xirr is None:
        if not _invested(account):
            row["xirr_unavailable_reason"] = "no_deposits_nor_opening_value"
        elif performance.days < MIN_DAYS:
            row["xirr_unavailable_reason"] = "period_too_short"
            row["xirr_min_days"] = MIN_DAYS
        else:
            row["xirr_unavailable_reason"] = "not_computable"
    return row


def _ceiling(account) -> dict | None:
    usage = account.ceiling_usage
    if usage is None:
        return None
    return {
        "ceiling": decimal(usage.ceiling),
        "contributed": decimal(usage.contributed),
        "remaining": decimal(usage.remaining),
        "used_pct": percent(usage.percent),
    }


def _summary(kind: str, account, holders: HolderResolver) -> dict:
    row = {
        "kind": kind,
        "id": account.pk,
        "name": str(account),
        "holder": holders.label(account),
        "is_active": account.is_active,
        "value": money(account.current_value),
        "last_value_date": to_json(_last_value_date(account)),
    }
    if isinstance(account, OtherAsset):
        row["category"] = account.get_category_display()
        return row
    row.update(
        type=str(account.account_type),
        institution=account.institution or "",
        opening_date=account.opening_date.isoformat(),
        **_performance(account),
    )
    if ceiling := _ceiling(account):
        row["deposit_ceiling"] = ceiling
    return row


@glad_tool()
def list_accounts(include_closed: bool = False) -> list[dict]:
    """Savings accounts, investment accounts (life insurance, PEA, securities
    account…) and other assets (vehicles, precious metals, crypto…) with
    their holder, current value, date of the latest value, annualized return
    (XIRR) and the use of the deposit ceiling of regulated envelopes. Use the
    kind and id with get_account. Without XIRR, xirr_unavailable_reason says
    why: no_deposits_nor_opening_value, period_too_short (the flows span less
    than xirr_min_days days: a shorter period is not meaningful once
    annualized) or not_computable."""
    holders = HolderResolver()
    rows = []
    for kind, model in MODELS.items():
        queryset = (
            model.objects.all()
            if include_closed
            else model.objects.filter(is_active=True)
        )
        if kind != "other":
            queryset = queryset.select_related("account_type")
        rows.extend(_summary(kind, account, holders) for account in queryset)
    return rows


def _holding(holding: InvestmentAccountHolding) -> dict:
    return {
        "id": holding.pk,
        "name": holding.name or holding.code or "",
        "isin": holding.isin or "",
        "asset_class": holding.asset_class or "unclassified",
        "quantity": quantity(holding.quantity),
        "value": money(holding.value),
        "initial_value": money(holding.initial_value),
        "initial_quantity": quantity(holding.initial_quantity),
    }


@glad_tool()
def get_account(kind: AccountKind, account_id: int, history: int = 24) -> dict:
    """One account or other asset: its details, its *history* latest values
    and deposits (with their id, origin and source), its holdings (investment
    accounts) and its annualized return (XIRR, nominal and after inflation)."""
    account = MODELS[kind].objects.get(pk=account_id)
    history = max(1, min(history, 500))
    details = _summary(kind, account, HolderResolver())
    if isinstance(account, OtherAsset):
        details.update(
            acquisition_date=to_json(account.acquisition_date),
            acquisition_value=money(account.acquisition_value),
            notes=account.notes,
            values=[
                {"date": to_json(v.value_date), "value": money(v.value)}
                for v in account.values.order_by("-value_date")[:history]
            ],
        )
        return details
    details.update(
        notes=account.commentaire or "",
        opening_value=money(account.opening_amount),
        deposits=[
            {
                "id": d.pk,
                "date": to_json(d.deposit_date),
                "amount": money(d.amount),
                "origin": d.origin,
                "source": d.source or "",
            }
            for d in account.deposits.order_by("-deposit_date")[:history]
        ],
    )
    if kind == "saving":
        details.update(
            interest_rate=to_json(account.interest_rate),
            values=[
                {"date": to_json(v.value_date), "value": money(v.value)}
                for v in account.values.order_by("-value_date")[:history]
            ],
        )
    else:
        details.update(
            cash=money(account.current_cash_value),
            cash_values=[
                {"date": to_json(v.value_date), "value": money(v.value)}
                for v in account.cash_values.order_by("-value_date")[:history]
            ],
            holdings=[
                _holding(holding)
                for holding in InvestmentAccountHolding.objects.filter(
                    account=account, is_active=True
                )
            ],
        )
    return details


def _holding_issues(holding: InvestmentAccountHolding) -> list[str]:
    issues = []
    if not holding.asset_class:
        issues.append("no_asset_class")
    if not holding.isin and holding.asset_class != AssetClass.EURO_FUND:
        issues.append("no_isin")
    return issues


def _account_issues(account) -> list[str]:
    issues = []
    if not _invested(account) and account.current_value.amount > 0:
        issues.append("no_deposits_nor_opening_value")
    if isinstance(account, SavingAccount) and not account.interest_rate:
        issues.append("no_interest_rate")
    usage = account.ceiling_usage
    if usage is not None and usage.contributed > usage.ceiling:
        issues.append("deposit_ceiling_exceeded")
    return issues


@glad_tool()
def get_data_quality_issues() -> list[dict]:
    """Data to complete in the active accounts: holdings without asset class
    (no_asset_class) or ISIN (no_isin, euro funds left aside), accounts with
    a value but neither deposit nor opening value
    (no_deposits_nor_opening_value: no XIRR),
    savings accounts without interest rate (no_interest_rate), envelopes over
    their deposit ceiling (deposit_ceiling_exceeded). Fix them with
    update_holding, update_account or add_account_deposit."""
    rows = []
    for kind in ("saving", "investment"):
        for account in (
            MODELS[kind].objects.filter(is_active=True).select_related("account_type")
        ):
            if issues := _account_issues(account):
                rows.append({"kind": kind, "account": ref(account), "issues": issues})
    holdings = InvestmentAccountHolding.objects.filter(
        is_active=True, account__is_active=True
    ).select_related("account__account_type")
    for holding in holdings:
        if issues := _holding_issues(holding):
            rows.append(
                {
                    "kind": "holding",
                    "holding_id": holding.pk,
                    "name": holding.name or holding.code or "",
                    "account": ref(holding.account),
                    "issues": issues,
                }
            )
    return rows
