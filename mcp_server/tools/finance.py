"""Savings accounts, investment accounts and other assets."""

from typing import Literal

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from finance.services.performance import account_performance
from mcp_server.serializers import money, to_json
from mcp_server.server import glad_tool

AccountKind = Literal["saving", "investment", "other"]

MODELS = {"saving": SavingAccount, "investment": InvestmentAccount, "other": OtherAsset}


def _summary(kind: str, account) -> dict:
    row = {
        "kind": kind,
        "id": account.pk,
        "name": str(account),
        "is_active": account.is_active,
        "value": money(account.current_value),
    }
    if kind == "other":
        row["category"] = account.get_category_display()
    else:
        row["type"] = str(account.account_type)
        row["institution"] = account.institution or ""
        row["opening_date"] = account.opening_date.isoformat()
    return row


@glad_tool()
def list_accounts(include_closed: bool = False) -> list[dict]:
    """Savings accounts, investment accounts (life insurance, PEA, securities
    account…) and other assets (vehicles, precious metals, crypto…) with
    their current value. Use the kind and id with get_account."""
    rows = []
    for kind, model in MODELS.items():
        queryset = (
            model.objects.all()
            if include_closed
            else model.objects.filter(is_active=True)
        )
        if kind != "other":
            queryset = queryset.select_related("account_type")
        rows.extend(_summary(kind, account) for account in queryset)
    return rows


@glad_tool()
def get_account(kind: AccountKind, account_id: int, history: int = 24) -> dict:
    """One account or other asset: its details, its *history* latest values
    and deposits, its holdings (investment accounts) and its annualized
    return (XIRR, nominal and after inflation)."""
    account = MODELS[kind].objects.get(pk=account_id)
    history = max(1, min(history, 500))
    details = _summary(kind, account)
    if isinstance(account, OtherAsset):
        details.update(
            acquisition_date=to_json(account.acquisition_date),
            acquisition_value=money(account.acquisition_value),
            notes=account.notes,
            values=[
                {"date": v.value_date.isoformat(), "value": money(v.value)}
                for v in account.values.order_by("-value_date")[:history]
            ],
        )
        return details
    details.update(
        notes=account.commentaire or "",
        opening_value=money(account.opening_amount),
        performance=to_json(account_performance(account)),
        deposits=[
            {"date": to_json(d.deposit_date), "amount": money(d.amount)}
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
                {"date": v.value_date.isoformat(), "value": money(v.value)}
                for v in account.cash_values.order_by("-value_date")[:history]
            ],
            holdings=[
                {
                    "id": holding.pk,
                    "name": holding.name or holding.code or "",
                    "isin": holding.isin or "",
                    "asset_class": holding.asset_class,
                    "quantity": to_json(holding.quantity),
                    "value": money(holding.value),
                    "initial_value": money(holding.initial_value),
                }
                for holding in InvestmentAccountHolding.objects.filter(
                    account=account, is_active=True
                )
            ],
        )
    return details
