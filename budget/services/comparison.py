"""Comparison of a budget with the previous year, and inflation from the INSEE CPI."""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from base.models import EconomicIndex, EconomicIndexValue
from budget.models import BudgetYear
from budget.services.summary import BudgetSummary, Indicators, build_budget
from finance.services.performance import cpi_at


def _cpi_values() -> list[EconomicIndexValue]:
    return list(
        EconomicIndexValue.objects.filter(index=EconomicIndex.CPI).order_by("period")
    )


def inflation_between(start: datetime.date, end: datetime.date) -> Decimal | None:
    """Change of the consumer price index from *start* to *end*, in percent."""
    values = _cpi_values()
    before, after = cpi_at(values, start), cpi_at(values, end)
    if not before or after is None:
        return None
    return (after / before - 1) * 100


def year_inflation(year: int) -> Decimal | None:
    """Inflation of *year* (December to December, or to the last published month)."""
    return inflation_between(
        datetime.date(year - 1, 12, 31), datetime.date(year, 12, 31)
    )


def last_12_months_inflation() -> Decimal | None:
    """Inflation over the last 12 published months, rounded to 0.1 %."""
    values = _cpi_values()
    if not values:
        return None
    last = values[-1].period
    change = inflation_between(last - relativedelta(months=12), last)
    if change is None:
        return None
    return change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def previous_year(budget_year: BudgetYear) -> BudgetYear | None:
    """Budget of the year before, if any."""
    return BudgetYear.objects.filter(year=budget_year.year - 1).first()


def compare(summary: BudgetSummary, previous: BudgetSummary) -> None:
    """Set the previous-year total of every node of *summary*.

    Nodes are matched by key: the same category, the same line (category,
    label and person), the same property or account.
    """
    totals: dict[str, Decimal] = {}
    for node in previous.nodes():
        totals[node.key] = totals.get(node.key, Decimal(0)) + node.total
    for node in summary.nodes():
        node.previous = totals.get(node.key, Decimal(0))
    summary.has_previous = True


def with_previous(
    summary: BudgetSummary,
) -> tuple[Indicators | None, Decimal | None]:
    """Compare *summary* with the previous year.

    Returns the indicators of the previous year (None without previous
    budget) and the inflation of the year, to read the changes in real terms.
    """
    budget_year = summary.budget_year
    previous = previous_year(budget_year)
    if previous is None:
        return None, None
    previous_summary = build_budget(
        previous, summary.perspective, currency=summary.currency
    )
    compare(summary, previous_summary)
    return previous_summary.indicators, year_inflation(budget_year.year)


def comparison_chart(summary: BudgetSummary) -> dict:
    """Totals of the top-level expense and savings groups, this year and the year before."""
    roots = [*summary.expenses, *summary.savings]
    return {
        "labels": [n.label for n in roots],
        "current": [round(float(n.total), 2) for n in roots],
        "previous": [round(float(n.previous or 0), 2) for n in roots],
    }
