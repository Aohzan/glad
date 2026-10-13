"""Tests of the budget models and the category tree."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from moneyed import Money

from budget.models import BudgetCategory, BudgetKind, BudgetLine
from budget.services.categories import category_tree, create_default_categories
from budget.tests.conftest import YEAR, add_line


@pytest.mark.django_db
class TestBudgetCategory:
    def test_path_depth_and_str(self, categories):
        energy = categories["energy"]
        assert energy.depth == 2
        assert energy.path == "Housing > Energy"
        assert str(energy) == "Housing > Energy"
        assert categories["housing"].depth == 1
        assert energy.ancestors() == [categories["housing"]]

    def test_descendant_ids(self, categories):
        housing = categories["housing"]
        assert housing.descendant_ids() == [categories["energy"].pk]
        assert BudgetCategory(name="Unsaved").descendant_ids() == []

    def test_child_takes_the_kind_of_its_parent(self, categories):
        child = BudgetCategory(
            name="Bonus", kind=BudgetKind.EXPENSE, parent=categories["salaries"]
        )
        child.full_clean()
        assert child.kind == BudgetKind.INCOME

    def test_cannot_be_its_own_parent(self, categories):
        housing = categories["housing"]
        housing.parent = housing
        with pytest.raises(ValidationError, match="under itself"):
            housing.clean()

    def test_cannot_be_placed_under_a_descendant(self, categories):
        housing = categories["housing"]
        housing.parent = categories["energy"]
        with pytest.raises(ValidationError, match="under itself"):
            housing.clean()

    def test_depth_is_limited(self, categories):
        third = BudgetCategory.objects.create(
            name="Electricity", kind=BudgetKind.EXPENSE, parent=categories["energy"]
        )
        fourth = BudgetCategory(name="Night", parent=third)
        with pytest.raises(ValidationError, match="3 levels"):
            fourth.clean()

    def test_moving_a_subtree_counts_its_height(self, categories):
        BudgetCategory.objects.create(
            name="Electricity", kind=BudgetKind.EXPENSE, parent=categories["energy"]
        )
        housing = categories["housing"]
        housing.parent = categories["loans"]
        with pytest.raises(ValidationError, match="3 levels"):
            housing.clean()

    def test_root_without_parent_is_valid(self, categories):
        categories["housing"].clean()

    def test_kind_change_reaches_the_descendants(self, categories):
        housing = categories["housing"]
        housing.kind = BudgetKind.SAVING
        housing.save()
        categories["energy"].refresh_from_db()
        assert categories["energy"].kind == BudgetKind.SAVING

    def test_root_names_are_unique_per_kind(self, categories):
        BudgetCategory.objects.create(name="Housing", kind=BudgetKind.INCOME)
        with pytest.raises(IntegrityError):
            BudgetCategory.objects.create(name="Housing", kind=BudgetKind.EXPENSE)


@pytest.mark.django_db
class TestBudgetLine:
    def test_amounts_and_str(self, categories, budget_year):
        line = add_line(budget_year, categories["energy"], 1200, label="Power")
        assert line.monthly_amount == Decimal(100)
        assert line.kind == BudgetKind.EXPENSE
        assert str(line) == f"{YEAR} - Power"
        assert str(budget_year) == str(YEAR)

    def test_negative_amount_is_refused(self, categories, budget_year):
        line = BudgetLine(
            budget_year=budget_year,
            category=categories["energy"],
            label="Refund",
            amount=Money(-5, "EUR"),
        )
        with pytest.raises(ValidationError):
            line.full_clean()


@pytest.mark.django_db
class TestCategories:
    def test_default_categories(self):
        created = create_default_categories()
        assert created > 20
        assert create_default_categories() == 0
        loans = BudgetCategory.objects.get(name="Loans", parent=None)
        assert loans.counts_as_debt
        assert loans.children.filter(counts_as_debt=True).count() == 2
        assert {c.kind for c in BudgetCategory.objects.all()} == set(BudgetKind.values)

    def test_tree_order(self, categories):
        tree = category_tree()
        paths = [node.path for node in tree]
        assert paths.index("Housing") < paths.index("Housing > Energy")
        assert paths[0] == "Salaries"
        assert paths[-1] == "Employee savings"
        assert [n.depth for n in tree if n.path == "Loans > Car loan"] == [2]
        assert [n.path for n in category_tree(BudgetKind.SAVING)] == [
            "Employee savings"
        ]
