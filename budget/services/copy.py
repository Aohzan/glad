"""Create the budget of a year from another one."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from moneyed import Money

from budget.models import BudgetLine, BudgetYear

CENT = Decimal("0.01")


@transaction.atomic
def copy_year(
    source: BudgetYear, year: int, revaluation: Decimal = Decimal(0)
) -> BudgetYear:
    """New budget for *year* with the settings and lines of *source*.

    Every amount is raised by *revaluation* percent (for instance the
    inflation of the past year) and rounded to the cent.
    """
    target = BudgetYear.objects.create(
        year=year,
        notes=source.notes,
        include_properties=source.include_properties,
        include_finance=source.include_finance,
    )
    target.excluded_properties.set(source.excluded_properties.all())
    factor = 1 + revaluation / 100
    BudgetLine.objects.bulk_create(
        BudgetLine(
            budget_year=target,
            category_id=line.category_id,
            label=line.label,
            amount=Money(
                (line.amount.amount * factor).quantize(CENT, rounding=ROUND_HALF_UP),
                line.amount.currency,
            ),
            person_id=line.person_id,
            notes=line.notes,
        )
        for line in source.lines.all()
    )
    return target
