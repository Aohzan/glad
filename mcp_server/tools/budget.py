"""Yearly budget of the household."""

from budget.models import BudgetYear
from budget.services.comparison import with_previous
from budget.services.summary import BudgetNode, build_budget
from mcp_server.serializers import decimal, to_json
from mcp_server.server import ToolInputError, glad_tool


def _node(node: BudgetNode) -> dict:
    row = {
        "label": node.label,
        "source": node.source,
        "total": decimal(node.total),
    }
    if node.line is not None:
        row["line_id"] = node.line.pk
    if node.person:
        row["person"] = node.person
    if node.previous is not None:
        row["previous_year"] = decimal(node.previous)
    if node.children:
        row["children"] = [_node(child) for child in node.children]
    return row


@glad_tool()
def get_budget(year: int) -> dict:
    """Budget of a year for the whole household: resources, expenses and
    savings as a tree of categories (yearly amounts, budget lines and the
    flows computed from the accounts and properties), the key indicators,
    and the totals of the previous year with the inflation of the year."""
    budget_year = BudgetYear.objects.filter(year=year).first()
    if budget_year is None:
        years = list(BudgetYear.objects.values_list("year", flat=True))
        raise ToolInputError(f"No budget for {year}. Budget years: {years}.")
    summary = build_budget(budget_year)
    previous, inflation = with_previous(summary)
    return {
        "year": year,
        "currency": summary.currency,
        "notes": budget_year.notes,
        "indicators": to_json(summary.indicators),
        "previous_indicators": to_json(previous),
        "inflation_pct": to_json(inflation),
        "resources": [_node(node) for node in summary.resources],
        "expenses": [_node(node) for node in summary.expenses],
        "savings": [_node(node) for node in summary.savings],
        "balance": _node(summary.balance) if summary.balance else None,
    }
