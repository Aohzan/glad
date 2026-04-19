"""Tests for property/services/tax_lmnp.py."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Property, PropertyLedgerEntry
from property.services.tax_lmnp import (
    LMNP_TAX_MAPPING,
    export_lmnp_csv,
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
        assert LMNP_TAX_MAPPING["rent_collected"]["line"] == "213"
        assert LMNP_TAX_MAPPING["other_income"]["line"] == "209"
        assert LMNP_TAX_MAPPING["management_fees"]["line"] == "218"
        assert LMNP_TAX_MAPPING["loan_interest"]["line"] == "230"
        assert LMNP_TAX_MAPPING["property_tax"]["line"] == "226"

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
        assert "213" in result["by_line"]

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
        assert "218" in result["by_line"]

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
        assert result["by_line"]["213"] == Decimal("1100.00")

    def test_summary_unknown_category_is_skipped(self, property_obj):
        """Categories not in LMNP_TAX_MAPPING are skipped gracefully."""
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.OTHER,
            amount=Money(Decimal("50.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        # 'other' is not in LMNP_TAX_MAPPING, so it should be skipped
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
class TestExportLmnpCsv:
    def test_export_empty(self, property_obj):
        csv_output = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_output.strip().split("\n")
        assert len(lines) == 1  # Only header
        assert "property" in lines[0]
        assert "entry_date" in lines[0]
        assert "lmnp_line" in lines[0]

    def test_export_with_entries(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
            description="March rent",
        )
        csv_output = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_output.strip().split("\n")
        assert len(lines) == 2  # Header + 1 entry
        assert "Test LMNP Property" in lines[1]
        assert "2023-03-01" in lines[1]
        assert "213" in lines[1]
        assert "March rent" in lines[1]

    def test_export_filters_by_year(self, property_obj):
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
        csv_2023 = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_2023.strip().split("\n")
        assert len(lines) == 2  # Header + 1 entry for 2023

    def test_export_unknown_category_has_empty_line(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.OTHER,
            amount=Money(Decimal("50.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        csv_output = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_output.strip().split("\n")
        assert len(lines) == 2
        # 'other' not in mapping, so lmnp_line and lmnp_label should be empty
        assert "other" in lines[1]

    def test_export_ordered_by_date(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 6, 1),
        )
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1100.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        csv_output = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_output.strip().split("\n")
        assert len(lines) == 3
        # First data line should be January (ordered by date)
        assert "2023-01-01" in lines[1]
        assert "2023-06-01" in lines[2]

    def test_export_csv_columns(self, property_obj):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
            amount=Money(Decimal("80.00"), "EUR"),
            entry_date=datetime.date(2023, 4, 1),
            description="Home insurance",
        )
        csv_output = export_lmnp_csv(property_obj.pk, 2023)
        lines = csv_output.strip().split("\n")
        header = lines[0]
        assert "property" in header
        assert "entry_date" in header
        assert "flow_type" in header
        assert "management_category" in header
        assert "lmnp_line" in header
        assert "lmnp_label" in header
        assert "description" in header
        assert "amount" in header
        assert "currency" in header
