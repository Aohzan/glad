"""Tests for property/services/tax_lmnp.py."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import (
    AmortizationAsset,
    ManagementCategory,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
)
from property.services.tax_lmnp import (
    get_amortization_schedule,
    get_bilan_data,
    get_fiscal_deficit_history,
    get_lmnp_summary,
)


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Test LMNP Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.mark.django_db
class TestManagementCategoryLmnpMetadata:
    def test_recettes_section(self):
        assert ManagementCategory.RENT_COLLECTED.lmnp_section == "recettes"
        assert ManagementCategory.CHARGES_COLLECTED.lmnp_section == "recettes"
        assert ManagementCategory.OTHER_INCOME.lmnp_section == "recettes"
        assert ManagementCategory.MANAGER_REVERSAL.lmnp_section == "recettes"

    def test_charges_section(self):
        assert ManagementCategory.MANAGEMENT_FEES.lmnp_section == "charges"
        assert ManagementCategory.LETTING_FEES.lmnp_section == "charges"
        assert ManagementCategory.MAINTENANCE.lmnp_section == "charges"
        assert ManagementCategory.INSURANCE.lmnp_section == "charges"
        assert ManagementCategory.FURNITURES.lmnp_section == "charges"
        assert ManagementCategory.RENTAL_GUARANTEE.lmnp_section == "charges"
        assert ManagementCategory.LOAN_INTEREST.lmnp_section == "charges"
        assert ManagementCategory.LOAN_INSURANCE.lmnp_section == "charges"
        assert ManagementCategory.PROPERTY_TAX.lmnp_section == "charges"
        assert ManagementCategory.CFE.lmnp_section == "charges"
        assert ManagementCategory.COOWNERSHIP.lmnp_section == "charges"
        assert ManagementCategory.WORKS.lmnp_section == "charges"
        assert ManagementCategory.OTHER_GENERAL_FEES.lmnp_section == "charges"
        assert ManagementCategory.MISC_DEDUCTIBLE.lmnp_section == "charges"

    def test_none_section_for_off_result(self):
        assert ManagementCategory.LOAN_REPAYMENT.lmnp_section is None
        assert ManagementCategory.DEPOSIT_IN.lmnp_section is None
        assert ManagementCategory.DEPOSIT_OUT.lmnp_section is None
        assert ManagementCategory.NON_DEDUCTIBLE.lmnp_section is None
        assert ManagementCategory.ALUR_WORKS_FUND.lmnp_section is None

    def test_alur_works_fund_has_no_cerfa_line(self):
        assert ManagementCategory.ALUR_WORKS_FUND.lmnp_line is None

    def test_cerfa_lines(self):
        assert ManagementCategory.RENT_COLLECTED.lmnp_line == "218"
        assert ManagementCategory.OTHER_INCOME.lmnp_line == "209"
        assert ManagementCategory.MANAGEMENT_FEES.lmnp_line == "242"
        assert ManagementCategory.LOAN_INTEREST.lmnp_line == "294"
        assert ManagementCategory.LOAN_INSURANCE.lmnp_line == "242"
        assert ManagementCategory.PROPERTY_TAX.lmnp_line == "244"

    def test_off_result_categories_have_no_cerfa_line(self):
        assert ManagementCategory.LOAN_REPAYMENT.lmnp_line is None
        assert ManagementCategory.DEPOSIT_IN.lmnp_line is None

    def test_all_categories_have_lmnp_label(self):
        for cat in ManagementCategory:
            assert cat.lmnp_label, f"Empty lmnp_label for {cat.value}"

    def test_all_categories_have_label(self):
        for cat in ManagementCategory:
            assert cat.label, f"Empty label for {cat.value}"

    def test_choices_is_django_compatible(self):
        """ManagementCategory.choices must be a list of (value, label) 2-tuples."""
        choices = ManagementCategory.choices
        assert isinstance(choices, list)
        assert len(choices) == len(ManagementCategory)
        for value, label in choices:
            assert isinstance(value, str)
            # label may be lazy string, just check it's truthy
            assert label

    def test_value_is_string(self):
        """Enum values must be plain strings for Django ORM field storage."""
        assert ManagementCategory.RENT_COLLECTED == "rent_collected"
        assert ManagementCategory.LOAN_INTEREST == "loan_interest"

    def test_section_none_implies_no_cerfa_line(self):
        """Every off-tax category (section=None) must have no cerfa line."""
        for cat in ManagementCategory:
            if cat.lmnp_section is None:
                assert cat.lmnp_line is None, (
                    f"{cat.value} has section=None but lmnp_line={cat.lmnp_line}"
                )


@pytest.mark.django_db
class TestGetLmnpSummary:
    def test_empty_summary(self, property_obj):
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["year"] == 2023
        assert result["recettes"] == Decimal("0")
        assert result["charges"] == Decimal("0")
        assert result["result"] == Decimal("0")
        assert result["by_category"] == {}
        assert result["by_line"] == {}

    def test_summary_with_rent_income(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("1200.00")
        assert result["charges"] == Decimal("0")
        assert result["result"] == Decimal("1200.00")
        assert "rent_collected" in result["by_category"]
        assert "218" in result["by_line"]

    def test_summary_with_charges_income(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.CHARGES_COLLECTED,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("100.00")

    def test_summary_with_deductible_expense(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGEMENT_FEES,
            amount=Money(Decimal("150.00"), "EUR"),
            entry_date=datetime.date(2023, 5, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["charges"] == Decimal("150.00")
        assert result["result"] == Decimal("-150.00")
        assert "242" in result["by_line"]

    def test_summary_result_is_recettes_minus_charges(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
            amount=Money(Decimal("200.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("1200.00")
        assert result["charges"] == Decimal("200.00")
        assert result["result"] == Decimal("1000.00")

    def test_summary_excludes_off_result_categories(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.DEPOSIT_IN,
            amount=Money(Decimal("2400.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.LOAN_REPAYMENT,
            amount=Money(Decimal("800.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        # deposit_in and loan_repayment have section=None, so not counted
        assert result["recettes"] == Decimal("0")
        assert result["charges"] == Decimal("0")

    def test_summary_filters_by_year(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2022, 6, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1300.00"), "EUR"),
            entry_date=datetime.date(2023, 6, 1),
        )
        result_2022 = get_lmnp_summary(property_obj.pk, 2022)
        result_2023 = get_lmnp_summary(property_obj.pk, 2023)
        assert result_2022["recettes"] == Decimal("1200.00")
        assert result_2023["recettes"] == Decimal("1300.00")

    def test_summary_by_line_aggregates_same_line(self, property_obj):
        # Both rent_collected and charges_collected map to line 213
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1000.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.CHARGES_COLLECTED,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["by_line"]["218"] == Decimal("1100.00")

    def test_summary_unknown_category_is_skipped(self, property_obj):
        """Off-tax categories (lmnp_section=None) are excluded from recettes and charges."""
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.NON_DEDUCTIBLE,
            amount=Money(Decimal("50.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        # 'non_deductible' has lmnp_section=None, so it must be excluded from the tax result
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("0")
        assert result["charges"] == Decimal("0")
        entry.delete()

    def test_summary_alur_works_fund_excluded_from_charges(self, property_obj):
        """ALUR works fund must not appear in taxable charges."""
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.ALUR_WORKS_FUND,
            amount=Money(Decimal("200.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["charges"] == Decimal("0"), (
            "ALUR works fund must not be in taxable charges"
        )
        assert result["recettes"] == Decimal("0")

    def test_summary_other_income_maps_to_line_209(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.OTHER_INCOME,
            amount=Money(Decimal("500.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["by_line"]["209"] == Decimal("500.00")

    def test_summary_manager_reversal_maps_to_recettes(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGER_REVERSAL,
            amount=Money(Decimal("300.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("300.00")

    def test_by_line_categories_present_and_includes_zeros(self, property_obj):
        """by_line_categories contains all mapped cerfa-line categories, even zeros."""
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1000.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        blc = result["by_line_categories"]

        # All cerfa lines with mapped categories should be present
        assert "218" in blc
        assert "242" in blc
        assert "244" in blc
        assert "294" in blc
        assert "recettes" in blc

        # Line 242 should have all exploitation categories including zeros
        line_242_keys = {cat["key"] for cat in blc["242"]}
        assert "management_fees" in line_242_keys
        assert "insurance" in line_242_keys
        assert "coownership" in line_242_keys
        assert "loan_insurance" in line_242_keys

        # Zero-value categories are included
        zero_cats = [cat for cat in blc["242"] if cat["amount"] == Decimal("0")]
        assert len(zero_cats) > 0

        # Non-zero rent_collected is reflected in "recettes" group
        rent = next(c for c in blc["recettes"] if c["key"] == "rent_collected")
        assert rent["amount"] == Decimal("1000.00")

    def test_by_line_categories_sorted_alphabetically(self, property_obj):
        """Each cerfa line's categories are sorted alphabetically by label."""
        result = get_lmnp_summary(property_obj.pk, 2023)
        for line, cats in result["by_line_categories"].items():
            labels = [c["label"] for c in cats]
            assert labels == sorted(labels), f"Line {line} not sorted: {labels}"


@pytest.mark.django_db
class TestLoanInsuranceClassification:
    """Verify that loan_insurance is classified as exploitation charge (line 242),
    not as a financial charge (line 294)."""

    def test_loan_insurance_ledger_entry_in_charges_exploitation(self, property_obj):
        """loan_insurance from ledger goes into charges_exploitation, not charges_financieres."""
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INSURANCE,
            amount=Money(Decimal("600.00"), "EUR"),
            entry_date=datetime.date(2023, 6, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["charges"] == Decimal("600.00")
        assert result["by_line"].get("242") == Decimal("600.00")
        assert "294" not in result["by_line"]

    def test_loan_insurance_from_ledger_entry_in_charges_exploitation(
        self, property_obj
    ):
        """loan_insurance ledger entry lands in line 242 (exploitation charges)."""
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INSURANCE,
            amount=Money(Decimal("999.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["by_line"].get("242", Decimal("0")) == Decimal("999.00")
        assert "294" not in result["by_line"]
        assert result["charges"] == Decimal("999.00")

    def test_year_before_first_asset_returns_empty(self):
        """When year < first acquisition year, should return {}."""
        prop = Property.objects.create(
            name="Deficit Prop",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        AmortizationAsset.objects.create(
            property=prop,
            label="Structure",
            beginning_date=datetime.date(2022, 1, 1),
            value_total=Money(80000, "EUR"),
            duration_years=75,
        )
        result = get_fiscal_deficit_history(prop.pk, 2021)
        assert result == {}

    def test_property_does_not_exist_returns_empty(self):
        """Non-existent property_id should return {}."""
        result = get_fiscal_deficit_history(999999, 2025)
        assert result == {}

    def test_no_deficit_no_history(self):
        """Property with no ledger entries and no assets has no deficit history."""
        prop = Property.objects.create(
            name="No Deficit",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        result = get_fiscal_deficit_history(prop.pk, 2025)
        assert result == {}

    def test_break_when_profit_absorbed_by_first_deficit(self):
        """When profit absorbs the first deficit and runs out, loop breaks (line 313)."""
        prop = Property.objects.create(
            name="Break Test",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        # Year 2020: deficit of 1000
        PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGEMENT_FEES,
            amount=Money(Decimal("1000"), "EUR"),
            entry_date=datetime.date(2020, 6, 1),
        )
        # Year 2021: another deficit of 500
        PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGEMENT_FEES,
            amount=Money(Decimal("500"), "EUR"),
            entry_date=datetime.date(2021, 6, 1),
        )
        # Year 2022: profit of 800 (less than first deficit 1000, triggers break)
        PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("800"), "EUR"),
            entry_date=datetime.date(2022, 6, 1),
        )
        result = get_fiscal_deficit_history(prop.pk, 2022)
        # 800 profit absorbs 800 of the 1000 deficit from 2020, leaving 200
        # 2021 deficit of 500 is untouched (loop broke)
        assert result[2020] == Decimal("200")
        assert result[2021] == Decimal("500")


@pytest.mark.django_db
class TestGetAmortizationSchedule:
    def test_empty_when_no_assets(self):
        prop = Property.objects.create(
            name="No Asset",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        result = get_amortization_schedule(prop.pk)
        assert result["rows"] == []
        assert result["total_depreciable_base"] == Decimal("0")
        assert result["amortized_to_date"] == Decimal("0")
        assert result["remaining"] == Decimal("0")
        assert result["end_year"] is None

    def test_schedule_has_rows_with_assets(self):
        prop = Property.objects.create(
            name="Asset Prop",
            property_type=Property.APARTMENT,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        AmortizationAsset.objects.create(
            property=prop,
            label="Gros œuvre",
            beginning_date=datetime.date(2020, 1, 1),
            value_total=Money(170000, "EUR"),
            duration_years=75,
        )
        result = get_amortization_schedule(prop.pk)
        assert len(result["rows"]) > 0
        assert result["total_depreciable_base"] == Decimal("170000")
        assert result["end_year"] == 2094  # 2020 + 75 - 1
        assert result["remaining"] >= Decimal("0")

    def test_schedule_row_structure(self):
        prop = Property.objects.create(
            name="Row Struct",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        AmortizationAsset.objects.create(
            property=prop,
            label="Agencements",
            beginning_date=datetime.date(2022, 1, 1),
            value_total=Money(10000, "EUR"),
            duration_years=12,
        )
        result = get_amortization_schedule(prop.pk)
        row = result["rows"][0]
        assert "year" in row
        assert "annual_dotation" in row
        assert "cumulative" in row
        assert "pct_complete" in row
        assert "per_asset" in row

    def test_schedule_asset_series(self):
        prop = Property.objects.create(
            name="Series Prop",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        AmortizationAsset.objects.create(
            property=prop,
            label="Étanchéité",
            beginning_date=datetime.date(2022, 1, 1),
            value_total=Money(5000, "EUR"),
            duration_years=15,
        )
        result = get_amortization_schedule(prop.pk)
        assert len(result["asset_series"]) == 1
        series = result["asset_series"][0]
        assert series["label"] == "Étanchéité"
        assert len(series["data"]) > 0


@pytest.mark.django_db
class TestGetBilanData:
    def test_bilan_property_does_not_exist_fallback(self):
        """get_bilan_data with non-existent property_id should not raise."""
        # Create a dummy property then delete it to get a valid ID that no longer exists
        prop = Property.objects.create(
            name="Temporary",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2022, 1, 1),
        )
        prop_id = prop.pk
        prop.delete()
        # Should not raise even with missing property
        result = get_bilan_data(prop_id, 2025)
        assert result["capital_individuel"] == Decimal("0")
        assert result["total_capitaux_propres"] == Decimal("0")

    def test_bilan_basic_fields_present(self):
        prop = Property.objects.create(
            name="Bilan Prop",
            property_type=Property.APARTMENT,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_bilan_data(prop.pk, 2025)
        assert "immobilisations_brutes" in result
        assert "amortissements_cumules" in result
        assert "valeur_nette_comptable" in result
        assert "emprunts" in result
        assert "resultat_exercice" in result
        assert "capital_individuel" in result

    def test_bilan_balance_sheet_equation(self):
        """capital_individuel + resultat_exercice + emprunts == valeur_nette_comptable."""
        prop = Property.objects.create(
            name="Balance Sheet Prop",
            property_type=Property.APARTMENT,
            buying_value=Money(150000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        result = get_bilan_data(prop.pk, 2025)
        assert (
            result["capital_individuel"]
            + result["resultat_exercice"]
            + result["emprunts"]
            == result["valeur_nette_comptable"]
        )


@pytest.mark.django_db
class TestAmortizationEntryFallbackForLoanInterest:
    """_get_category_totals_for_year should use amortization entries when no manual loan_interest entries exist."""

    def _make_property(self, name="Amort Fallback Prop"):
        return Property.objects.create(
            name=name,
            property_type=Property.APARTMENT,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )

    def _make_loan(self, prop):
        return PropertyLoan.objects.create(
            property=prop,
            original_amount=Money(150000, "EUR"),
            interest_rate=Decimal("3.5"),
            start_date=datetime.date(2020, 2, 1),
            end_date=datetime.date(2045, 2, 1),
            monthly_payment=Money(750, "EUR"),
        )

    def test_uses_amortization_entries_when_no_ledger_entries(self):
        """When no loan_interest ledger entries exist, the amortization table interest is used."""
        from property.services.tax_lmnp import _get_category_totals_for_year

        prop = self._make_property()
        loan = self._make_loan(prop)

        # Create amortization entries for 2022 (3 months)
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2022, 1, 1),
            capital=Money(Decimal("500"), "EUR"),
            interest=Money(Decimal("437.50"), "EUR"),
            remaining_balance_amount=Money(Decimal("149500"), "EUR"),
        )
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2022, 2, 1),
            capital=Money(Decimal("502"), "EUR"),
            interest=Money(Decimal("435.50"), "EUR"),
            remaining_balance_amount=Money(Decimal("148998"), "EUR"),
        )

        totals = _get_category_totals_for_year(prop.pk, 2022)
        assert "loan_interest" in totals
        assert totals["loan_interest"] == Decimal("437.50") + Decimal("435.50")

    def test_manual_ledger_entries_take_precedence(self):
        """When manual loan_interest ledger entries exist, they override amortization entries."""
        from property.services.tax_lmnp import _get_category_totals_for_year

        prop = self._make_property("Precedence Prop")
        loan = self._make_loan(prop)

        # Manual ledger entry for loan_interest
        PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
            amount=Money(Decimal("1200"), "EUR"),
            entry_date=datetime.date(2022, 6, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        )

        # Create amortization entry with different value
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2022, 6, 1),
            capital=Money(Decimal("500"), "EUR"),
            interest=Money(Decimal("437.50"), "EUR"),
            remaining_balance_amount=Money(Decimal("149500"), "EUR"),
        )

        totals = _get_category_totals_for_year(prop.pk, 2022)
        # Should use the manual ledger entry (1200), not the amortization entry (437.50)
        assert totals["loan_interest"] == Decimal("1200")

    def test_no_amortization_entries_defaults_to_zero(self):
        """When no ledger entries and no amortization entries, loan_interest is absent/zero."""
        from property.services.tax_lmnp import _get_category_totals_for_year

        prop = self._make_property("Zero Prop")
        self._make_loan(prop)

        totals = _get_category_totals_for_year(prop.pk, 2022)
        # No amortization entries → loan_interest not in totals (defaults to 0)
        assert totals.get("loan_interest", Decimal("0")) == Decimal("0")

    def test_amortization_entries_outside_year_not_counted(self):
        """Only amortization entries within the requested year are summed."""
        from property.services.tax_lmnp import _get_category_totals_for_year

        prop = self._make_property("Year Filter Prop")
        loan = self._make_loan(prop)

        # Entry in 2022 (included)
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2022, 6, 1),
            capital=Money(Decimal("500"), "EUR"),
            interest=Money(Decimal("300"), "EUR"),
            remaining_balance_amount=Money(Decimal("149500"), "EUR"),
        )
        # Entry in 2021 (excluded when querying 2022)
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2021, 12, 1),
            capital=Money(Decimal("495"), "EUR"),
            interest=Money(Decimal("999"), "EUR"),
            remaining_balance_amount=Money(Decimal("150000"), "EUR"),
        )

        totals = _get_category_totals_for_year(prop.pk, 2022)
        assert totals["loan_interest"] == Decimal("300")

    def test_lmnp_summary_uses_amortization_interest(self):
        """get_lmnp_summary charges_financieres reflects amortization entry interest."""
        prop = self._make_property("LMNP Summary Amort Prop")
        loan = self._make_loan(prop)

        # Add rent income
        PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("800"), "EUR"),
            entry_date=datetime.date(2022, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        )

        # Create amortization entries for 2022
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=datetime.date(2022, 1, 1),
            capital=Money(Decimal("500"), "EUR"),
            interest=Money(Decimal("437.50"), "EUR"),
            remaining_balance_amount=Money(Decimal("149500"), "EUR"),
        )

        summary = get_lmnp_summary(prop.pk, 2022)
        assert summary["charges_financieres"] == Decimal("437.50")
        assert summary["charges"] == Decimal("437.50")
