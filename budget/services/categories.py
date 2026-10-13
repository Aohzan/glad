"""The category tree of the budgets: default categories and ordered listing."""

from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext as _

from budget.models import BudgetCategory, BudgetKind


def _default_tree() -> list[tuple[str, str, list[str], bool]]:
    """(kind, name, sub-category names, counts as debt) of the default categories."""
    income, expense, saving = BudgetKind.INCOME, BudgetKind.EXPENSE, BudgetKind.SAVING
    return [
        (income, _("Salaries"), [], False),
        (income, _("Bonuses and profit-sharing"), [], False),
        (income, _("Self-employed income"), [], False),
        (income, _("Benefits and allowances"), [], False),
        (income, _("Pensions"), [], False),
        (income, _("Other income"), [], False),
        (
            expense,
            _("Housing"),
            [
                _("Rent"),
                _("Energy"),
                _("Water"),
                _("Internet and phone"),
                _("Home insurance"),
                _("Maintenance and works"),
            ],
            False,
        ),
        (expense, _("Food"), [_("Groceries"), _("Restaurants")], False),
        (
            expense,
            _("Transport"),
            [
                _("Fuel and charging"),
                _("Car insurance"),
                _("Car maintenance"),
                _("Public transport"),
            ],
            False,
        ),
        (expense, _("Loans"), [_("Car loan"), _("Consumer credit")], True),
        (
            expense,
            _("Taxes"),
            [_("Income tax"), _("Property tax"), _("Housing tax")],
            False,
        ),
        (expense, _("Health"), [_("Health insurance"), _("Medical expenses")], False),
        (expense, _("Children"), [_("Childcare"), _("School"), _("Activities")], False),
        (expense, _("Leisure and holidays"), [], False),
        (expense, _("Subscriptions"), [], False),
        (expense, _("Insurance"), [], False),
        (expense, _("Clothing"), [], False),
        (expense, _("Gifts and donations"), [], False),
        (expense, _("Miscellaneous"), [], False),
        (saving, _("Savings outside the application"), [], False),
        (saving, _("Employee savings"), [], False),
    ]


@transaction.atomic
def create_default_categories() -> int:
    """Create the default category tree in the active language.

    Categories that already exist with the same name are kept. Returns the
    number of categories created.
    """
    created = 0
    for position, (kind, name, children, debt) in enumerate(_default_tree()):
        root, is_new = BudgetCategory.objects.get_or_create(
            parent=None,
            kind=kind,
            name=name,
            defaults={"position": position, "counts_as_debt": debt},
        )
        created += is_new
        for child_position, child in enumerate(children):
            _child, is_new = BudgetCategory.objects.get_or_create(
                parent=root,
                name=child,
                defaults={
                    "kind": kind,
                    "position": child_position,
                    "counts_as_debt": debt,
                },
            )
            created += is_new
    return created


@dataclass(frozen=True)
class CategoryNode:
    """A category with its depth, in tree order."""

    category: BudgetCategory
    depth: int
    path: str


def category_tree(kind: str | None = None) -> list[CategoryNode]:
    """Every category in tree order (parents before their children), in one query."""
    categories = list(BudgetCategory.objects.all())
    if kind is not None:
        categories = [c for c in categories if c.kind == kind]
    children: dict[int | None, list[BudgetCategory]] = {}
    for category in categories:
        children.setdefault(category.parent_id, []).append(category)
    order = {k: i for i, k in enumerate(BudgetKind.values)}
    nodes: list[CategoryNode] = []

    def walk(parent_id: int | None, depth: int, prefix: str) -> None:
        for category in sorted(
            children.get(parent_id, []),
            key=lambda c: (order[c.kind], c.position, c.name.lower()),
        ):
            path = f"{prefix} > {category.name}" if prefix else category.name
            nodes.append(CategoryNode(category, depth, path))
            walk(category.pk, depth + 1, path)

    walk(None, 1, "")
    return nodes
