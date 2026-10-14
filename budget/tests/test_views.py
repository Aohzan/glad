"""Tests of the budget pages."""

import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from moneyed import Money

from budget.forms import MAX_IMPORT_SIZE, CategoryChoiceField
from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from budget.tests.conftest import YEAR, add_line
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
)


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.fixture
def filled_year(categories, budget_year, user):
    add_line(budget_year, categories["salaries"], 30000, "Salary", user)
    add_line(budget_year, categories["energy"], 2400, "Power")
    return budget_year


@pytest.mark.django_db
class TestIndex:
    def test_without_categories(self, user_client):
        response = user_client.get(reverse("budget:index"))
        assert response.status_code == 200
        assert not response.context["has_categories"]
        assert "Create the default categories" in response.content.decode()

    def test_without_budget(self, user_client, categories):
        response = user_client.get(reverse("budget:index"))
        assert "No budget yet." in response.content.decode()

    def test_with_budgets(self, user_client, filled_year):
        response = user_client.get(reverse("budget:index"))
        year, indicators = response.context["rows"][0]
        assert year == filled_year
        assert indicators.income == Decimal(30000)
        assert reverse("budget:year", args=[YEAR]) in response.content.decode()
        assert response.context["evolution"] is None

    def test_evolution_over_the_years(self, user_client, filled_year, categories):
        later = BudgetYear.objects.create(
            year=YEAR + 1, include_properties=False, include_finance=False
        )
        add_line(later, categories["salaries"], 32000)
        add_line(later, categories["savings"], 1000)
        response = user_client.get(reverse("budget:index"))
        assert response.context["evolution"] == {
            "years": [str(YEAR), str(YEAR + 1)],
            "income": [30000.0, 32000.0],
            "expenses": [2400.0, 0.0],
            "savings": [0.0, 1000.0],
        }
        assert 'id="budget-evolution-data"' in response.content.decode()


@pytest.mark.django_db
class TestYearDetail:
    def test_household(self, user_client, filled_year):
        response = user_client.get(reverse("budget:year", args=[YEAR]))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="budget-sankey-data"' in content
        assert f'<option value="{YEAR}" selected>' in content
        assert "`/budget/${year}/`" in content
        assert response.context["person"] is None
        assert response.context["previous"] is None
        assert response.context["deltas"] is None
        assert response.context["comparison_chart"] is None
        assert response.context["sankey"]["total"] == 30000

    def test_person_and_previous_year(self, user_client, filled_year, categories, user):
        previous = BudgetYear.objects.create(
            year=YEAR - 1, include_properties=False, include_finance=False
        )
        add_line(previous, categories["salaries"], 28000, "Salary", user)
        response = user_client.get(
            reverse("budget:year", args=[YEAR]), {"person": user.pk}
        )
        assert response.context["person"] == user
        assert response.context["indicators"].income == Decimal(30000)
        assert response.context["deltas"]["income"] == Decimal(2000)
        assert response.context["comparison_chart"]["labels"] == ["Housing"]
        content = response.content.decode()
        assert f"{YEAR - 1} compared with {YEAR}" in content
        assert f"`/budget/${{year}}/?person={user.pk}`" in content

    def test_warns_about_guessed_origins(self, user_client, filled_year):
        filled_year.include_finance = True
        filled_year.save()
        kind = SavingAccountType.objects.create(name="Booklet", code="BKT")
        account = SavingAccount.objects.create(
            account_type=kind,
            name="Booklet",
            opening_date=datetime.date(2000, 1, 1),
            opening_value=Money(0, "EUR"),
        )
        SavingAccountDeposit.objects.create(
            account=account,
            amount=Money(500, "EUR"),
            deposit_date=datetime.datetime(YEAR, 3, 1),
        )
        response = user_client.get(reverse("budget:year", args=[YEAR]))
        content = response.content.decode()
        assert 'id="budget-guesses"' in content
        assert "1 account movement of unknown origin" in content
        assert f"/finance/saving/{account.pk}/#deposits-panel" in content

    def test_unknown_person_shows_the_household(self, user_client, filled_year):
        response = user_client.get(
            reverse("budget:year", args=[YEAR]), {"person": "999999"}
        )
        assert response.status_code == 200
        assert response.context["person"] is None

    def test_unknown_year(self, user_client):
        assert user_client.get(reverse("budget:year", args=[1950])).status_code == 404


@pytest.mark.django_db
class TestYearForms:
    def test_create(self, user_client):
        response = user_client.get(reverse("budget:year_new"))
        assert response.status_code == 200
        response = user_client.post(
            reverse("budget:year_new"),
            {"year": YEAR, "include_properties": "on", "notes": "First"},
        )
        assert response.url == reverse("budget:year", args=[YEAR])
        budget_year = BudgetYear.objects.get(year=YEAR)
        assert budget_year.include_properties
        assert not budget_year.include_finance

    def test_create_suggests_a_free_year(self, user_client, budget_year):
        with mock.patch("budget.views.datetime") as clock:
            clock.date.today.return_value.year = YEAR
            response = user_client.get(reverse("budget:year_new"))
        assert response.context["form"].initial["year"] == YEAR + 1

    def test_invalid(self, user_client, budget_year):
        response = user_client.post(reverse("budget:year_new"), {"year": YEAR})
        assert response.status_code == 200
        assert response.context["form"].errors["year"]

    def test_edit(self, user_client, budget_year):
        url = reverse("budget:year_edit", args=[YEAR])
        assert user_client.get(url).status_code == 200
        response = user_client.post(url, {"year": YEAR, "notes": "Updated"})
        assert response.status_code == 302
        budget_year.refresh_from_db()
        assert budget_year.notes == "Updated"

    def test_delete(self, user_client, filled_year):
        url = reverse("budget:year_delete", args=[YEAR])
        assert user_client.get(url).status_code == 405
        response = user_client.post(url)
        assert response.url == reverse("budget:index")
        assert not BudgetYear.objects.exists()
        assert not BudgetLine.objects.exists()

    def test_copy(self, user_client, filled_year):
        url = reverse("budget:year_copy", args=[YEAR])
        response = user_client.get(url)
        assert response.context["form"].initial["year"] == YEAR + 1
        response = user_client.post(url, {"year": YEAR + 1, "revaluation": "10"})
        assert response.url == reverse("budget:year", args=[YEAR + 1])
        copied = BudgetYear.objects.get(year=YEAR + 1)
        assert copied.lines.get(label="Power").amount.amount == Decimal(2640)

    def test_copy_to_an_existing_year(self, user_client, filled_year):
        response = user_client.post(
            reverse("budget:year_copy", args=[YEAR]), {"year": YEAR, "revaluation": "0"}
        )
        assert response.status_code == 200
        assert "already exists" in str(response.context["form"].errors["year"])


@pytest.mark.django_db
class TestLineForms:
    def test_needs_categories(self, user_client, budget_year):
        response = user_client.get(reverse("budget:line_new", args=[YEAR]))
        assert response.url == reverse("budget:categories")

    def test_create(self, user_client, categories, budget_year, user):
        url = reverse("budget:line_new", args=[YEAR])
        response = user_client.get(url, {"category": categories["energy"].pk})
        assert response.context["form"].initial["category"] == categories["energy"].pk
        field = response.context["form"].fields["category"]
        assert isinstance(field, CategoryChoiceField)
        assert [label for label, _choices in field.choices] == [
            "Income",
            "Expenses",
            "Savings",
        ]
        response = user_client.post(
            url,
            {
                "category": categories["energy"].pk,
                "label": "Gas",
                "amount_0": "900",
                "amount_1": "EUR",
                "person": user.pk,
            },
        )
        assert response.url == reverse("budget:year", args=[YEAR])
        line = BudgetLine.objects.get(label="Gas")
        assert line.person == user
        assert line.budget_year == budget_year

    def test_save_and_add_another(self, user_client, categories, budget_year):
        response = user_client.post(
            reverse("budget:line_new", args=[YEAR]),
            {
                "category": categories["energy"].pk,
                "label": "Water",
                "amount_0": "300",
                "amount_1": "EUR",
                "save_add": "1",
            },
        )
        assert response.url.endswith(f"?category={categories['energy'].pk}")

    def test_invalid(self, user_client, categories, budget_year):
        response = user_client.post(
            reverse("budget:line_new", args=[YEAR]),
            {
                "category": categories["energy"].pk,
                "label": "",
                "amount_0": "-1",
                "amount_1": "EUR",
            },
        )
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_edit_and_delete(self, user_client, filled_year):
        line = filled_year.lines.get(label="Power")
        url = reverse("budget:line_edit", args=[line.pk])
        assert user_client.get(url).status_code == 200
        response = user_client.post(
            url,
            {
                "category": line.category_id,
                "label": "Power",
                "amount_0": "2000",
                "amount_1": "EUR",
            },
        )
        assert response.status_code == 302
        line.refresh_from_db()
        assert line.amount.amount == Decimal(2000)
        delete_url = reverse("budget:line_delete", args=[line.pk])
        assert user_client.get(delete_url).status_code == 405
        response = user_client.post(delete_url)
        assert response.url == reverse("budget:year", args=[YEAR])
        assert not BudgetLine.objects.filter(pk=line.pk).exists()


@pytest.mark.django_db
class TestCategoryViews:
    def test_list(self, user_client, categories):
        response = user_client.get(reverse("budget:categories"))
        kinds = [kind for kind, _label, _nodes in response.context["groups"]]
        assert kinds == BudgetKind.values
        assert "Housing" in response.content.decode()

    def test_create_under_a_parent(self, user_client, categories):
        url = reverse("budget:category_new")
        response = user_client.get(url, {"parent": categories["housing"].pk})
        assert response.context["form"].initial["parent"] == categories["housing"].pk
        response = user_client.post(
            url,
            {
                "name": "Water",
                "parent": categories["housing"].pk,
                "kind": BudgetKind.INCOME,
                "position": 1,
            },
        )
        assert response.url == reverse("budget:categories")
        water = BudgetCategory.objects.get(name="Water")
        assert water.kind == BudgetKind.EXPENSE

    def test_edit_excludes_the_subtree(self, user_client, categories):
        url = reverse("budget:category_edit", args=[categories["housing"].pk])
        response = user_client.get(url)
        choices = response.context["form"].fields["parent"].queryset
        assert categories["housing"] not in choices
        assert categories["energy"] not in choices
        response = user_client.post(
            url,
            {
                "name": "Home",
                "kind": BudgetKind.EXPENSE,
                "position": 0,
                "parent": categories["energy"].pk,
            },
        )
        assert response.status_code == 200
        response = user_client.post(
            url, {"name": "Home", "kind": BudgetKind.EXPENSE, "position": 0}
        )
        assert response.status_code == 302
        categories["housing"].refresh_from_db()
        assert categories["housing"].name == "Home"

    def test_delete(self, user_client, filled_year, categories):
        response = user_client.post(
            reverse("budget:category_delete", args=[categories["housing"].pk])
        )
        assert response.url == reverse("budget:categories")
        assert "move or delete them first" in _messages(response)[0]
        response = user_client.post(
            reverse("budget:category_delete", args=[categories["savings"].pk])
        )
        assert _messages(response)[-1] == "Category deleted."
        assert not BudgetCategory.objects.filter(pk=categories["savings"].pk).exists()

    def test_defaults(self, user_client):
        url = reverse("budget:category_defaults")
        assert user_client.get(url).status_code == 405
        response = user_client.post(url, {"next": "index"})
        assert response.url == reverse("budget:index")
        assert BudgetCategory.objects.count() > 20
        response = user_client.post(url)
        assert response.url == reverse("budget:categories")
        assert _messages(response)[-1] == "0 categories created."


def _upload(text: str, name="budget.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
class TestCsvViews:
    def test_export(self, user_client, filled_year):
        response = user_client.get(reverse("budget:export", args=[YEAR]))
        assert response["Content-Type"].startswith("text/csv")
        assert f"budget-{YEAR}.csv" in response["Content-Disposition"]
        assert response.content.decode("utf-8-sig").startswith("kind;category")

    def test_import_preview_and_confirm(self, user_client, categories, budget_year):
        url = reverse("budget:import", args=[YEAR])
        assert user_client.get(url).status_code == 200
        text = "category;amount;label\nHousing > Energy;1200;Power\nUnknown;5;Bad\n"
        response = user_client.post(url, {"csv_file": _upload(text)})
        assert response.status_code == 200
        preview = response.context["preview"]
        assert len(preview.valid_rows) == 1
        assert len(preview.invalid_rows) == 1
        response = user_client.post(reverse("budget:import_confirm", args=[YEAR]))
        assert response.url == reverse("budget:year", args=[YEAR])
        assert _messages(response) == [
            "1 line imported.",
            "1 line with errors was skipped.",
        ]
        assert budget_year.lines.get().label == "Power"

    def test_import_creates_missing_categories(
        self, user_client, categories, budget_year
    ):
        text = "kind;category;amount\nexpense;Leisure;300\n"
        user_client.post(
            reverse("budget:import", args=[YEAR]),
            {"csv_file": _upload(text), "create_missing": "on"},
        )
        response = user_client.post(reverse("budget:import_confirm", args=[YEAR]))
        assert _messages(response) == ["1 line imported."]
        assert BudgetCategory.objects.filter(name="Leisure").exists()

    def test_import_file_errors(self, user_client, budget_year):
        url = reverse("budget:import", args=[YEAR])
        response = user_client.post(url, {"csv_file": _upload("label\nA\n")})
        assert response.status_code == 200
        assert _messages(response) == ["Missing columns: category, amount"]
        big = SimpleUploadedFile("big.csv", b"x" * (MAX_IMPORT_SIZE + 1))
        response = user_client.post(url, {"csv_file": big})
        assert response.context["form"].errors["csv_file"]

    def test_confirm_without_session(self, user_client, budget_year):
        response = user_client.post(reverse("budget:import_confirm", args=[YEAR]))
        assert response.url == reverse("budget:import", args=[YEAR])
        assert "expired" in _messages(response)[0]

    def test_confirm_for_another_year(self, user_client, categories, budget_year):
        BudgetYear.objects.create(year=YEAR + 1)
        user_client.post(
            reverse("budget:import", args=[YEAR]),
            {"csv_file": _upload("category;amount\nSalaries;1\n")},
        )
        response = user_client.post(reverse("budget:import_confirm", args=[YEAR + 1]))
        assert response.url == reverse("budget:import", args=[YEAR + 1])

    def test_ai_prompt(self, user_client, categories, budget_year):
        response = user_client.get(reverse("budget:ai_prompt", args=[YEAR]))
        assert response.status_code == 200
        assert "Housing &gt; Energy" in response.content.decode()
