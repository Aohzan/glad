"""Data of the sankey diagram of a budget: resources on the left, uses on the right."""

from dataclasses import replace
from decimal import Decimal

from django.utils.translation import gettext as _

from budget.services.summary import (
    ACCOUNT_DEPOSITS,
    ACCOUNT_WITHDRAWALS,
    BudgetNode,
    BudgetSummary,
)


def _node(node: BudgetNode) -> dict:
    assigned = node.line is not None and node.line.person_id is not None  # ty: ignore[unresolved-attribute]
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


def _net_account_flows(
    left: list[BudgetNode], right: list[BudgetNode]
) -> tuple[list[BudgetNode], list[BudgetNode]]:
    """Deduct the withdrawals from the deposits of the accounts, or the reverse.

    Money taken from a savings account to the current account and put on
    another one is a movement inside the household: the diagram shows the
    net savings only, the bigger side reduced by the smaller one, each of its
    accounts in proportion.
    """
    deposits = next((n for n in right if n.key == ACCOUNT_DEPOSITS), None)
    withdrawals = next((n for n in left if n.key == ACCOUNT_WITHDRAWALS), None)
    if deposits is None or withdrawals is None:
        return left, right
    if deposits.total >= withdrawals.total:
        kept, dropped, label = deposits, withdrawals, _("Net account deposits")
    else:
        kept, dropped, label = withdrawals, deposits, _("Net withdrawals from savings")
    ratio = (kept.total - dropped.total) / kept.total
    net = replace(
        kept,
        label=label,
        children=[
            replace(c, amount=c.total * ratio, children=[]) for c in kept.children
        ],
    )

    def swap(nodes: list[BudgetNode]) -> list[BudgetNode]:
        return [net if n is kept else n for n in nodes if n is not dropped]

    return swap(left), swap(right)


def sankey_payload(summary: BudgetSummary) -> dict:
    """Two trees joined by a central node, ready for ``json_script``.

    The left tree holds the resources (and the deficit, if any), the right
    one the expenses, the savings and the money left; both sum to the same
    total. The withdrawals from the accounts are deducted from their deposits.
    """
    left, right = _net_account_flows(
        list(summary.resources), [*summary.expenses, *summary.savings]
    )
    balance = summary.balance
    if balance is not None:
        (right if balance.kind == "saving" else left).append(balance)
    return {
        "currency": summary.currency,
        "center": _("Budget"),
        "total": round(float(sum((n.total for n in left), Decimal(0))), 2),
        "left": [_node(n) for n in left if n.total > 0],
        "right": [_node(n) for n in right if n.total > 0],
    }
