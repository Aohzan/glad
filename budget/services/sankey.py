"""Data of the sankey diagram of a budget: resources on the left, uses on the right."""

from dataclasses import replace
from decimal import Decimal

from django.utils.translation import gettext as _

from budget.services.summary import (
    ACCOUNT_DEPOSITS,
    ACCOUNT_EXCEPTIONAL,
    ACCOUNT_INVESTMENTS,
    ACCOUNT_WITHDRAWALS,
    BudgetNode,
    BudgetSummary,
    balance_node,
)

#: Groups of the account deposits, netted with the withdrawals.
_DEPOSIT_GROUPS = (ACCOUNT_DEPOSITS, ACCOUNT_INVESTMENTS)
#: Groups hidden by the view without the exceptional flows.
_EXCEPTIONAL_GROUPS = (ACCOUNT_WITHDRAWALS, ACCOUNT_EXCEPTIONAL)


def _node(node: BudgetNode) -> dict:
    assigned = node.line is not None and node.line.person_id is not None
    return {
        "id": node.key,
        "label": node.label,
        # Lines of the whole household keep no name.
        "person": node.person if assigned else "",
        "value": round(float(node.total), 2),
        "kind": node.kind,
        "source": node.source,
        "children": [_node(child) for child in node.children if child.total > 0],
    }


def _scaled(node: BudgetNode, ratio: Decimal, label: str | None = None) -> BudgetNode:
    """*node* with each child multiplied by *ratio*."""
    return replace(
        node,
        label=label or node.label,
        children=[
            replace(c, amount=c.total * ratio, children=[]) for c in node.children
        ],
    )


def _net_account_flows(
    left: list[BudgetNode], right: list[BudgetNode]
) -> tuple[list[BudgetNode], list[BudgetNode]]:
    """Deduct the withdrawals from the deposits of the accounts, or the reverse.

    Money taken from a savings account to the current account and put on
    another one is a movement inside the household: the diagram shows the
    net savings only, the bigger side reduced by the smaller one, each of its
    accounts in proportion.
    """
    deposits = [n for n in right if n.key in _DEPOSIT_GROUPS]
    withdrawals = next((n for n in left if n.key == ACCOUNT_WITHDRAWALS), None)
    if not deposits or withdrawals is None:
        return left, right
    deposited = sum((n.total for n in deposits), Decimal(0))
    if deposited >= withdrawals.total:
        ratio = (deposited - withdrawals.total) / deposited
        netted = {id(n): _scaled(n, ratio) for n in deposits}
        return (
            [n for n in left if n is not withdrawals],
            [netted.get(id(n), n) for n in right],
        )
    ratio = (withdrawals.total - deposited) / withdrawals.total
    net = _scaled(withdrawals, ratio, _("Net withdrawals from savings"))
    return (
        [net if n is withdrawals else n for n in left],
        [n for n in right if n.key not in _DEPOSIT_GROUPS],
    )


def _side(nodes: list[BudgetNode]) -> list[dict]:
    return [_node(n) for n in nodes if n.total > 0]


def _view(
    left: list[BudgetNode], right: list[BudgetNode], deficit_label: str | None = None
) -> dict:
    """Both sides, the balance added to the smaller one so that they match."""
    left, right = list(left), list(right)
    difference = sum((n.total for n in left), Decimal(0)) - sum(
        (n.total for n in right), Decimal(0)
    )
    balance = balance_node(difference.quantize(Decimal("0.01")), deficit_label)
    if balance is not None:
        (right if difference > 0 else left).append(balance)
    left_dicts = _side(left)
    return {
        "total": round(sum(n["value"] for n in left_dicts), 2),
        "left": left_dicts,
        "right": _side(right),
    }


def sankey_payload(summary: BudgetSummary) -> dict:
    """Two trees joined by a central node, ready for ``json_script``.

    The left tree holds the resources (and the untracked resources, if any),
    the right one the expenses, the savings and the money left; both sum to
    the same total. The withdrawals from the accounts are deducted from their
    deposits. When the budget has withdrawals or exceptional deposits,
    ``regular`` holds the same diagram without them: the income against the
    expenses and the savings.
    """
    resources = list(summary.resources)
    uses = [*summary.expenses, *summary.savings]
    payload = {
        "currency": summary.currency,
        "center": _("Budget"),
        "others": _("Others"),
        **_view(*_net_account_flows(resources, uses)),
        "regular": None,
    }
    if any(n.key in _EXCEPTIONAL_GROUPS for n in resources):
        payload["regular"] = _view(
            [n for n in resources if n.key not in _EXCEPTIONAL_GROUPS],
            uses,
            _("Other resources"),
        )
    return payload
