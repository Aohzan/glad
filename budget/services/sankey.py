"""Data of the sankey diagram of a budget: resources on the left, uses on the right."""

from decimal import Decimal

from django.utils.translation import gettext as _

from budget.services.summary import BudgetNode, BudgetSummary


def _node(node: BudgetNode) -> dict:
    return {
        "id": node.key,
        "label": node.label,
        "value": round(float(node.total), 2),
        "kind": node.kind,
        "source": node.source,
        "children": [_node(child) for child in node.children if child.total > 0],
    }


def sankey_payload(summary: BudgetSummary) -> dict:
    """Two trees joined by a central node, ready for ``json_script``.

    The left tree holds the resources (and the deficit, if any), the right
    one the expenses, the savings and the money left; both sum to the same
    total.
    """
    left = list(summary.resources)
    right = [*summary.expenses, *summary.savings]
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
