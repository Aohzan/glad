"""Tests of the CSV export and import of budget lines, and of the AI prompt."""

from decimal import Decimal

import pytest

from budget.models import BudgetCategory, BudgetKind, BudgetYear
from budget.services.csv_io import (
    MAX_ROWS,
    ai_prompt,
    export_lines,
    import_lines,
    parse_lines,
)
from budget.tests.conftest import YEAR, add_line


@pytest.fixture
def alice(django_user_model):
    return django_user_model.objects.create_user(username="alice", first_name="Alice")


@pytest.mark.django_db
class TestExport:
    def test_round_trip(self, categories, budget_year, alice):
        add_line(budget_year, categories["energy"], Decimal("1450.5"), "Power")
        add_line(budget_year, categories["salaries"], 42000, "Salary", alice)
        text = export_lines(budget_year)
        assert text.splitlines()[0] == "kind;category;label;amount;person;notes"
        assert "expense;Housing > Energy;Power;1450.50;;" in text
        assert "income;Salaries;Salary;42000.00;alice;" in text
        target = BudgetYear.objects.create(year=YEAR + 1)
        preview = parse_lines(text)
        assert preview.errors == []
        assert import_lines(target, preview, "EUR") == 2
        imported = {line.label: line for line in target.lines.all()}
        assert imported["Power"].category == categories["energy"]
        assert imported["Power"].amount.amount == Decimal("1450.50")
        assert imported["Salary"].person == alice


@pytest.mark.django_db
class TestFormulas:
    def test_exported_cells_cannot_run_as_formulas(self, categories, budget_year):
        line = add_line(budget_year, categories["energy"], 10, "=1+2")
        line.notes = "+cmd"
        line.save()
        text = export_lines(budget_year)
        assert ";'=1+2;" in text
        assert ";'+cmd" in text
        preview = parse_lines(text)
        assert preview.rows[0].label == "=1+2"
        assert preview.rows[0].notes == "+cmd"


@pytest.mark.django_db
class TestParse:
    def test_french_file(self, categories, alice):
        text = (
            "Type;Catégorie;Libellé;Montant;Personne;Commentaire\n"
            "dépense; housing >  ENERGY ;Électricité;-1 200,50;;facture\n"
            "revenu;Salaries;Salaire;3.500,00;Alice;\n"
            "\n"
            ";Loans > Car loan;;300;foyer;\n"
        )
        preview = parse_lines(text)
        assert preview.errors == []
        assert [row.errors for row in preview.rows] == [[], [], []]
        power, salary, car = preview.rows
        assert power.category == categories["energy"]
        assert power.amount == Decimal("1200.50")
        assert power.kind == BudgetKind.EXPENSE
        assert power.notes == "facture"
        assert salary.person_id == alice.pk
        assert salary.person_label == "Alice"
        assert salary.amount == Decimal("3500.00")
        assert car.kind == BudgetKind.EXPENSE
        assert car.label == "Car loan"
        assert car.person_id is None

    def test_amounts_are_checked(self, categories):
        text = (
            "category;amount\nSalaries;12,345\nSalaries;NaN\nSalaries;1000000000000\n"
        )
        rows = parse_lines(text).rows
        assert rows[0].amount == Decimal("12.35")
        assert rows[1].errors == ["Invalid amount: NaN"]
        assert rows[2].errors == ["The amount is too large."]

    def test_comma_separated(self, categories):
        preview = parse_lines('category,amount\nSalaries,"1,234.56"\n')
        assert preview.rows[0].amount == Decimal("1234.56")

    def test_file_errors(self, categories):
        assert parse_lines("").errors == ["The file is empty."]
        assert parse_lines("label;notes\nA;B\n").errors == [
            "Missing columns: category, amount"
        ]
        assert parse_lines("category;amount\n").errors == ["The file has no line."]
        too_long = "category;amount\n" + "Salaries;1\n" * (MAX_ROWS + 1)
        assert parse_lines(too_long).errors == [
            f"The file has more than {MAX_ROWS} lines."
        ]

    def test_line_errors(self, categories):
        text = (
            "kind;category;label;amount;person\n"
            "income;Salaries;A;abc;\n"
            "wrong;Salaries;B;1;\n"
            "income;;C;1;\n"
            "income;Unknown;D;1;\n"
            "expense;Salaries;E;1;\n"
            "income;Salaries;F;1;Nobody\n"
            f"income;Salaries;{'x' * 250};1;\n"
        )
        preview = parse_lines(text)
        errors = [row.errors for row in preview.rows]
        assert errors[0] == ["Invalid amount: abc"]
        assert errors[1] == ["Unknown kind: wrong"]
        assert errors[2] == ["The category is missing."]
        assert errors[3] == ["Unknown category: Unknown"]
        assert errors[4] == ["The category Salaries is not of kind Expenses."]
        assert errors[5] == ["Unknown person: Nobody"]
        assert errors[6] == ["The label is too long."]
        assert preview.valid_rows == []
        assert len(preview.invalid_rows) == 7

    def test_missing_categories(self, categories):
        text = (
            "kind;category;label;amount\n"
            "expense;Housing > Insurance;Home;300\n"
            "expense;housing > insurance;Again;100\n"
            "expense;Leisure > Sport;Gym;500\n"
            ";Hobbies;No kind;1\n"
            "income;Housing > Rent;Wrong side;1\n"
            "income;Leisure > Sport;Twice;1\n"
            "income;Leisure > Ski;Same parent;1\n"
            "expense;A > B > C > D;Too deep;1\n"
            f"expense;Leisure > {'x' * 101};Long name;1\n"
        )
        assert parse_lines(text).missing_categories == []
        preview = parse_lines(text, create_missing=True)
        assert preview.missing_categories == ["Housing > Insurance", "Leisure > Sport"]
        errors = [row.errors for row in preview.rows]
        assert errors[:3] == [[], [], []]
        assert errors[3] == ["The kind is needed to create the category Hobbies."]
        assert errors[4] == ["The category Housing is not of kind Income."]
        assert errors[5] == ["The category Leisure > Sport is used with several kinds."]
        assert errors[6] == ["The category Leisure > Ski is used with several kinds."]
        assert errors[7] == ["Categories are limited to 3 levels."]
        assert errors[8] == ["The category name is too long."]

        budget_year = BudgetYear.objects.create(year=YEAR)
        assert import_lines(budget_year, preview, "EUR") == 3
        insurance = BudgetCategory.objects.get(name="Insurance")
        assert insurance.parent == categories["housing"]
        assert insurance.kind == BudgetKind.EXPENSE
        assert insurance.lines.count() == 2
        sport = BudgetCategory.objects.get(name="Sport")
        assert sport.parent.name == "Leisure"
        assert sport.parent.parent is None


@pytest.mark.django_db
class TestPrompt:
    def test_prompt_lists_the_categories_and_members(
        self, categories, budget_year, alice
    ):
        prompt = ai_prompt(budget_year)
        assert str(YEAR) in prompt
        assert "kind;category;label;amount;person;notes" in prompt
        assert "- Housing > Energy" in prompt
        assert "expense (Expenses):" in prompt
        assert "Alice" in prompt

    def test_prompt_skips_the_kinds_without_category(self, categories, budget_year):
        categories["savings"].delete()
        assert "saving (" not in ai_prompt(budget_year)
