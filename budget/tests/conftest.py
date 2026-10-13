"""Fixtures of the budget tests.

The session fixtures hold a demo budget; the budget tests start from empty
budget tables instead, so their totals only count what they create.
"""

import datetime

import pytest
from moneyed import Money

from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from budget.services.perspective import Perspective

#: A year without any flow in the session fixtures.
YEAR = 2001


@pytest.fixture(autouse=True)
def empty_budget(db):
    """Remove the demo budget of the session fixtures."""
    BudgetLine.objects.all().delete()
    BudgetYear.objects.all().delete()
    while BudgetCategory.objects.exists():
        BudgetCategory.objects.filter(children__isnull=True).delete()


@pytest.fixture
def household():
    """The whole household seen from two adults."""
    return Perspective(person_id=None, members=frozenset({1, 2}), adults=2)


@pytest.fixture
def categories():
    """A small tree: salaries, housing > energy, loans (debt) and savings."""
    salaries = BudgetCategory.objects.create(name="Salaries", kind=BudgetKind.INCOME)
    housing = BudgetCategory.objects.create(name="Housing", kind=BudgetKind.EXPENSE)
    energy = BudgetCategory.objects.create(
        name="Energy", kind=BudgetKind.EXPENSE, parent=housing
    )
    loans = BudgetCategory.objects.create(
        name="Loans", kind=BudgetKind.EXPENSE, counts_as_debt=True
    )
    car = BudgetCategory.objects.create(
        name="Car loan", kind=BudgetKind.EXPENSE, parent=loans
    )
    savings = BudgetCategory.objects.create(
        name="Employee savings", kind=BudgetKind.SAVING
    )
    return {
        "salaries": salaries,
        "housing": housing,
        "energy": energy,
        "loans": loans,
        "car": car,
        "savings": savings,
    }


@pytest.fixture
def budget_year():
    """An empty budget without automatic flows."""
    return BudgetYear.objects.create(
        year=YEAR, include_properties=False, include_finance=False
    )


def add_line(budget_year, category, amount, label=None, person=None):
    """Create a budget line of *amount* euros."""
    return BudgetLine.objects.create(
        budget_year=budget_year,
        category=category,
        label=label or category.name,
        amount=Money(amount, "EUR"),
        person=person,
    )


def day(month: int, dom: int = 1, year: int = YEAR) -> datetime.date:
    """A date of the test year."""
    return datetime.date(year, month, dom)
