"""Tests for property/services/tax_lmnp.py."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import AmortizationAsset, Property, PropertyLedgerEntry
from property.services.tax_lmnp import (
    LMNP_TAX_MAPPING,
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
class TestLmnpTaxMapping:
    def test_mapping_has_recettes_section(self):
        assert LMNP_TAX_MAPPING["rent_collected"]["section"] == "recettes"
        assert LMNP_TAX_MAPPING["charges_collected"]["section"] == "recettes"
        assert LMNP_TAX_MAPPING["other_income"]["section"] == "recettes"
        assert LMNP_TAX_MAPPING["manager_reversal"]["section"] == "recettes"

    def test_mapping_has_charges_section(self):
        assert LMNP_TAX_MAPPING["management_fees"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["maintenance"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["insurance"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["loan_interest"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["loan_insurance"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["property_tax"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["cfe"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["coownership"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["works"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["other_general_fees"]["section"] == "charges"
        assert LMNP_TAX_MAPPING["misc_deductible"]["section"] == "charges"

    def test_mapping_has_none_section_for_off_result(self):
        assert LMNP_TAX_MAPPING["loan_repayment"]["section"] is None
        assert LMNP_TAX_MAPPING["deposit_in"]["section"] is None
        assert LMNP_TAX_MAPPING["deposit_out"]["section"] is None
        assert LMNP_TAX_MAPPING["non_deductible"]["section"] is None

    def test_mapping_has_cerfa_lines(self):
        assert LMNP_TAX_MAPPING["rent_collected"]["line"] == "218"
        assert LMNP_TAX_MAPPING["other_income"]["line"] == "209"
        assert LMNP_TAX_MAPPING["management_fees"]["line"] == "242"
        assert LMNP_TAX_MAPPING["loan_interest"]["line"] == "294"
        assert LMNP_TAX_MAPPING["property_tax"]["line"] == "244"

    def test_mapping_none_section_has_no_line(self):
        assert LMNP_TAX_MAPPING["loan_repayment"]["line"] is None
        assert LMNP_TAX_MAPPING["deposit_in"]["line"] is None

    def test_mapping_has_labels(self):
        for key, value in LMNP_TAX_MAPPING.items():
            assert "label" in value, f"Missing label for {key}"
            assert value["label"], f"Empty label for {key}"


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
        """Categories not in LMNP_TAX_MAPPING are skipped gracefully."""
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.NON_DEDUCTIBLE,
            amount=Money(Decimal("50.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        # 'non_deductible' is not in LMNP_TAX_MAPPING, so it should be skipped
        result = get_lmnp_summary(property_obj.pk, 2023)
        assert result["recettes"] == Decimal("0")
        assert result["charges"] == Decimal("0")
        entry.delete()

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


@pytest.mark.django_db
class TestGetFiscalDeficitHistory:
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
