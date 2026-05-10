"""Tests for get_lmnp_checklist() in property/services/tax_lmnp.py."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import (
    AmortizationSetup,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAnnualStatement,
)
from property.services.tax_lmnp import get_lmnp_checklist

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def lmnp_property():
    return Property.objects.create(
        name="Test LMNP",
        property_type=Property.APARTMENT,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )


@pytest.fixture
def amortization_setup(lmnp_property):
    setup = AmortizationSetup.objects.create(
        property=lmnp_property,
        total_value=Money(200_000, "EUR"),
        land_percentage=Decimal("15.00"),
    )
    setup.initialize_components()
    return setup


def _add_entry(prop, category, amount=1000, year=2024, flow_type=None):
    if flow_type is None:
        income_cats = {
            "rent_collected",
            "charges_collected",
            "other_income",
            "manager_reversal",
            "deposit_in",
        }
        flow_type = (
            PropertyLedgerEntry.FlowType.INCOME
            if category in income_cats
            else PropertyLedgerEntry.FlowType.EXPENSE
        )
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=flow_type,
        management_category=category,
        amount=Money(Decimal(str(amount)), "EUR"),
        entry_date=datetime.date(year, 6, 1),
    )


def _add_loan(prop, year=2024, name=None):
    return PropertyLoan.objects.create(
        property=prop,
        name=name or "Loan",
        start_date=datetime.date(year, 1, 1),
        end_date=datetime.date(year + 20, 1, 1),
        original_amount=Money(150_000, "EUR"),
        interest_rate=Decimal("1.5"),
        insurance_rate=Decimal("0.1"),
    )


def _add_loan_statement(loan, year=2024):
    return PropertyLoanAnnualStatement.objects.create(
        loan=loan,
        year=year,
        interest_amount=Money(2_000, "EUR"),
        insurance_amount=Money(300, "EUR"),
    )


# ─── Individual check tests ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestChecklistRevenues:
    def test_revenues_missing_when_no_entry(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "missing"
        assert check["count"] == 0

    def test_revenues_ok_when_entry_present(self, lmnp_property):
        _add_entry(lmnp_property, "rent_collected", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "ok"
        assert check["count"] == 1

    def test_revenues_ok_for_each_revenue_category(self, lmnp_property):
        for cat in ("charges_collected", "other_income", "manager_reversal"):
            _add_entry(lmnp_property, cat, year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "ok"

    def test_revenues_missing_for_different_year(self, lmnp_property):
        _add_entry(lmnp_property, "rent_collected", year=2023)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "missing"


@pytest.mark.django_db
class TestChecklistCharges:
    def test_charges_warning_when_absent(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "charges"
        )
        assert check["status"] == "warning"

    def test_charges_ok_when_entry_present(self, lmnp_property):
        _add_entry(lmnp_property, "management_fees", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "charges"
        )
        assert check["status"] == "ok"

    def test_charges_ok_for_multiple_categories(self, lmnp_property):
        for cat in ("maintenance", "insurance", "coownership", "works"):
            _add_entry(lmnp_property, cat, year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "charges"
        )
        assert check["status"] == "ok"
        assert check["count"] == 4


@pytest.mark.django_db
class TestChecklistTaxes:
    def test_taxes_warning_when_absent(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(c for c in result["properties"][0]["checks"] if c["id"] == "taxes")
        assert check["status"] == "warning"

    def test_taxes_ok_with_property_tax(self, lmnp_property):
        _add_entry(lmnp_property, "property_tax", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(c for c in result["properties"][0]["checks"] if c["id"] == "taxes")
        assert check["status"] == "ok"

    def test_taxes_ok_with_cfe(self, lmnp_property):
        _add_entry(lmnp_property, "cfe", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(c for c in result["properties"][0]["checks"] if c["id"] == "taxes")
        assert check["status"] == "ok"


@pytest.mark.django_db
class TestChecklistFinancialCharges:
    def test_na_when_no_loan(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "na"

    def test_warning_when_loan_but_no_entries(self, lmnp_property):
        _add_loan(lmnp_property, year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "warning"

    def test_warning_when_loan_and_interest_entry_but_no_statement(self, lmnp_property):
        """Loan with ledger entries but missing bank statement → warning."""
        _add_loan(lmnp_property, year=2024)
        _add_entry(lmnp_property, "loan_interest", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "warning"

    def test_warning_when_loan_and_insurance_entry_but_no_statement(
        self, lmnp_property
    ):
        """Loan with ledger entries but missing bank statement → warning."""
        _add_loan(lmnp_property, year=2024)
        _add_entry(lmnp_property, "loan_insurance", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "warning"

    def test_ok_when_loan_with_annual_statement(self, lmnp_property):
        """Loan with annual statement and entries → ok."""
        loan = _add_loan(lmnp_property, year=2024)
        _add_loan_statement(loan, year=2024)
        _add_entry(lmnp_property, "loan_interest", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "ok"

    def test_ok_when_statement_counts_even_without_ledger_entries(self, lmnp_property):
        """Annual statement with no ledger entries still counts as fin_count=1."""
        loan = _add_loan(lmnp_property, year=2024)
        _add_loan_statement(loan, year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "ok"

    def test_warning_with_loans_missing_statement_names_in_detail(self, lmnp_property):
        """Loan name appears in warning detail when statement is missing."""
        _add_loan(lmnp_property, year=2024, name="Crédit Agricole")
        _add_entry(lmnp_property, "loan_interest", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "warning"
        assert "Crédit Agricole" in check["detail"]

    def test_warning_with_partial_statements_two_loans(self, lmnp_property):
        """Two loans, only one with a statement → warning listing the missing loan."""
        loan1 = _add_loan(lmnp_property, year=2024, name="Loan A")
        loan2 = PropertyLoan.objects.create(
            property=lmnp_property,
            name="Loan B",
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2044, 1, 1),
            original_amount=Money(50_000, "EUR"),
            interest_rate=Decimal("2.0"),
            insurance_rate=Decimal("0.15"),
        )
        _add_loan_statement(loan1, year=2024)
        _add_entry(lmnp_property, "loan_interest", year=2024)
        # loan2 has no statement
        del loan2  # ensure it exists in DB, variable not needed
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "warning"
        assert "Loan B" in check["detail"]

    def test_na_when_loan_ended_before_year(self, lmnp_property):
        """Loan ended before the checked year — not active, so N/A."""
        PropertyLoan.objects.create(
            property=lmnp_property,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            original_amount=Money(100_000, "EUR"),
            interest_rate=Decimal("1.5"),
            insurance_rate=Decimal("0.1"),
        )
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "financial_charges"
        )
        assert check["status"] == "na"


@pytest.mark.django_db
class TestChecklistAmortization:
    def test_setup_missing_when_no_setup(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "amortization_setup"
        )
        assert check["status"] == "missing"

    def test_setup_ok_when_present(self, lmnp_property, amortization_setup):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "amortization_setup"
        )
        assert check["status"] == "ok"

    def test_components_missing_when_no_setup(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "amortization_components"
        )
        assert check["status"] == "missing"

    def test_components_warning_when_setup_but_no_assets(self, lmnp_property):
        AmortizationSetup.objects.create(
            property=lmnp_property,
            total_value=Money(200_000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        # No components — setup exists but initialize_components() not called
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "amortization_components"
        )
        assert check["status"] == "warning"

    def test_components_ok_when_setup_and_assets(
        self, lmnp_property, amortization_setup
    ):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c
            for c in result["properties"][0]["checks"]
            if c["id"] == "amortization_components"
        )
        assert check["status"] == "ok"
        assert (
            check["count"] == 5
        )  # 5 standard components created by initialize_components


@pytest.mark.django_db
class TestChecklistBuyingValue:
    def test_ok_when_buying_value_set(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "buying_value"
        )
        assert check["status"] == "ok"

    def test_missing_when_buying_value_zero(self):
        prop = Property.objects.create(
            name="Zero Value Property",
            property_type=Property.APARTMENT,
            buying_value=Money(0, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_lmnp_checklist([prop], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "buying_value"
        )
        assert check["status"] == "missing"


# ─── Overall status & form readiness ─────────────────────────────────────────


@pytest.mark.django_db
class TestChecklistOverallStatus:
    def test_incomplete_when_revenues_missing(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        assert result["overall_status"] == "incomplete"

    def test_warning_when_only_non_required_missing(
        self, lmnp_property, amortization_setup
    ):
        """Setup + components + revenues present, charges/taxes absent → warning."""
        _add_entry(lmnp_property, "rent_collected", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        # taxes and charges are warning-level, not missing → overall = warning
        assert result["overall_status"] == "warning"

    def test_ok_when_all_data_present(self, lmnp_property, amortization_setup):
        _add_entry(lmnp_property, "rent_collected", year=2024)
        _add_entry(lmnp_property, "management_fees", year=2024)
        _add_entry(lmnp_property, "property_tax", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        # No loan so financial_charges is N/A — no warnings
        assert result["overall_status"] == "ok"

    def test_total_issues_counts_warnings_and_missing(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        # revenues=missing, charges=warning, taxes=warning, financial_charges=na,
        # amortization_setup=missing, amortization_components=missing, buying_value=ok
        assert result["total_issues"] == result["properties"][0]["issue_count"]

    def test_total_issues_zero_when_all_ok(self, lmnp_property, amortization_setup):
        _add_entry(lmnp_property, "rent_collected", year=2024)
        _add_entry(lmnp_property, "management_fees", year=2024)
        _add_entry(lmnp_property, "property_tax", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        assert result["total_issues"] == 0


@pytest.mark.django_db
class TestChecklistForms:
    def test_forms_contains_all_expected_ids(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_ids = {f["id"] for f in result["forms"]}
        assert "2031" in form_ids
        assert "2033a" in form_ids
        assert "2033b" in form_ids
        assert "2033c" in form_ids
        assert "2033d" in form_ids
        assert "suiv39c" in form_ids
        assert "2042c" in form_ids
        assert "2033e" in form_ids
        assert "2033f" in form_ids
        assert "2033g" in form_ids

    def test_2033d_is_auto(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2033d = next(f for f in result["forms"] if f["id"] == "2033d")
        assert form_2033d["status"] == "auto"

    def test_optional_forms_are_na(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        for fid in ("2033e", "2033f", "2033g"):
            form = next(f for f in result["forms"] if f["id"] == fid)
            assert form["status"] == "na"
            assert form["required"] is False

    def test_2033b_incomplete_when_revenues_missing(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2033b = next(f for f in result["forms"] if f["id"] == "2033b")
        assert form_2033b["status"] == "incomplete"

    def test_2033c_incomplete_when_no_setup(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2033c = next(f for f in result["forms"] if f["id"] == "2033c")
        assert form_2033c["status"] == "incomplete"

    def test_2033c_ok_when_setup_and_components(
        self, lmnp_property, amortization_setup
    ):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2033c = next(f for f in result["forms"] if f["id"] == "2033c")
        assert form_2033c["status"] == "ok"

    def test_2031_incomplete_when_revenues_missing(self, lmnp_property):
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2031 = next(f for f in result["forms"] if f["id"] == "2031")
        assert form_2031["status"] == "incomplete"

    def test_2031_ok_when_revenues_present(self, lmnp_property, amortization_setup):
        _add_entry(lmnp_property, "rent_collected", year=2024)
        result = get_lmnp_checklist([lmnp_property], 2024)
        form_2031 = next(f for f in result["forms"] if f["id"] == "2031")
        assert form_2031["status"] == "ok"


# ─── Multiple properties ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestChecklistMultipleProperties:
    def test_all_properties_listed(self, lmnp_property):
        prop2 = Property.objects.create(
            name="Second LMNP",
            property_type=Property.APARTMENT,
            buying_value=Money(150_000, "EUR"),
            buying_date=datetime.date(2021, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_lmnp_checklist([lmnp_property, prop2], 2024)
        assert len(result["properties"]) == 2

    def test_issues_aggregated_across_properties(self, lmnp_property):
        prop2 = Property.objects.create(
            name="Second LMNP",
            property_type=Property.APARTMENT,
            buying_value=Money(150_000, "EUR"),
            buying_date=datetime.date(2021, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_lmnp_checklist([lmnp_property, prop2], 2024)
        total = sum(p["issue_count"] for p in result["properties"])
        assert result["total_issues"] == total

    def test_one_ok_one_incomplete_gives_incomplete(
        self, lmnp_property, amortization_setup
    ):
        """If one property is complete but another is not, overall = incomplete."""
        _add_entry(lmnp_property, "rent_collected", year=2024)
        _add_entry(lmnp_property, "management_fees", year=2024)
        _add_entry(lmnp_property, "property_tax", year=2024)

        prop2 = Property.objects.create(
            name="Incomplete LMNP",
            property_type=Property.APARTMENT,
            buying_value=Money(100_000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_lmnp_checklist([lmnp_property, prop2], 2024)
        assert result["overall_status"] == "incomplete"

    def test_empty_properties_list(self):
        result = get_lmnp_checklist([], 2024)
        assert result["properties"] == []
        assert result["total_issues"] == 0
        assert result["overall_status"] == "ok"


# ─── Recurring entries ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestChecklistRecurringEntries:
    def test_recurring_revenue_in_year_is_counted(self, lmnp_property):
        """A monthly recurring entry starting 2023 should count for 2024."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category="rent_collected",
            amount=Money(800, "EUR"),
            entry_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2025, 12, 31),
        )
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "ok"

    def test_recurring_entry_ended_before_year_not_counted(self, lmnp_property):
        """Recurring entry ended in 2022 should not count for 2024."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category="rent_collected",
            amount=Money(800, "EUR"),
            entry_date=datetime.date(2020, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2022, 12, 31),
        )
        result = get_lmnp_checklist([lmnp_property], 2024)
        check = next(
            c for c in result["properties"][0]["checks"] if c["id"] == "revenues"
        )
        assert check["status"] == "missing"
