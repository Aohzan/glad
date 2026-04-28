"""Tests for property/models/ledger.py."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from moneyed import Money

from property.models import Lease, Property, PropertyLedgerEntry


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def income_entry(property_obj):
    return PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal("1200.00"), "EUR"),
        entry_date=datetime.date(2023, 3, 1),
        description="March rent",
    )


@pytest.mark.django_db
class TestPropertyLedgerEntryStr:
    def test_str_non_recurring(self, income_entry):
        result = str(income_entry)
        assert "Test Property" in result
        assert "2023-03-01" in result

    def test_str_recurring_monthly(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
        )
        result = str(entry)
        assert "Test Property" in result
        assert "Monthly" in result or "monthly" in result.lower()

    def test_str_recurring_yearly(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
            amount=Money(Decimal("500.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
        )
        result = str(entry)
        assert "Test Property" in result
        assert "Yearly" in result or "yearly" in result.lower()


@pytest.mark.django_db
class TestPropertyLedgerEntryClean:
    def test_clean_valid_income_entry(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        entry.clean()  # Should not raise

    def test_clean_valid_expense_entry(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        entry.clean()  # Should not raise

    def test_clean_negative_amount_raises(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("-100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        with pytest.raises(ValidationError) as exc_info:
            entry.clean()
        assert "amount" in str(exc_info.value).lower() or "Amount" in str(
            exc_info.value
        )

    def test_clean_zero_amount_raises(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("0.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        with pytest.raises(ValidationError):
            entry.clean()

    def test_clean_income_with_expense_category_raises(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        with pytest.raises(ValidationError):
            entry.clean()

    def test_clean_expense_with_income_category_raises(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        with pytest.raises(ValidationError):
            entry.clean()

    def test_clean_expense_with_deposit_in_raises(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.DEPOSIT_IN,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        with pytest.raises(ValidationError):
            entry.clean()

    def test_clean_income_with_manager_reversal_valid(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGER_REVERSAL,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        entry.clean()  # Should not raise

    def test_clean_no_amount_does_not_raise(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=None,
            entry_date=datetime.date(2023, 3, 1),
        )
        entry.clean()  # Should not raise when amount is None


@pytest.mark.django_db
class TestPropertyLedgerEntryGetManagementCategoryDisplay:
    def test_known_category_returns_label(self, income_entry):
        display = income_entry.get_management_category_display()
        assert display  # Should return a non-empty string
        assert isinstance(display, str)

    def test_unknown_category_returns_raw_value(self, property_obj):
        entry = PropertyLedgerEntry(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category="unknown_cat",
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2023, 3, 1),
        )
        display = entry.get_management_category_display()
        assert display == "unknown_cat"


@pytest.mark.django_db
class TestPropertyLedgerEntryGetLmnpLine:
    def test_known_category_returns_line(self, income_entry):
        line = income_entry.get_lmnp_line()
        assert line == "218"

    def test_off_result_category_returns_none(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.DEPOSIT_IN,
            amount=Money(Decimal("2400.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        assert entry.get_lmnp_line() is None

    def test_expense_category_returns_line(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
            amount=Money(Decimal("300.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        assert entry.get_lmnp_line() == "294"


@pytest.mark.django_db
class TestPropertyLedgerEntryGenerateOccurrences:
    def test_non_recurring_generates_one_occurrence(self, income_entry):
        occurrences = income_entry.generate_occurrences()
        assert len(occurrences) == 1
        assert occurrences[0]["date"] == datetime.date(2023, 3, 1)

    def test_monthly_recurring_generates_multiple(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1200.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2023, 3, 31),
        )
        occurrences = entry.generate_occurrences()
        assert len(occurrences) == 3  # Jan, Feb, Mar

    def test_yearly_recurring_generates_multiple(self, property_obj):
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
            amount=Money(Decimal("500.00"), "EUR"),
            entry_date=datetime.date(2021, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
            recurrence_end_date=datetime.date(2023, 12, 31),
        )
        occurrences = entry.generate_occurrences()
        assert len(occurrences) == 3  # 2021, 2022, 2023


@pytest.mark.django_db
class TestPropertyLedgerEntryAliases:
    def test_none_alias(self):
        assert PropertyLedgerEntry.NONE == PropertyLedgerEntry.RecurrenceType.NONE

    def test_monthly_alias(self):
        assert PropertyLedgerEntry.MONTHLY == PropertyLedgerEntry.RecurrenceType.MONTHLY

    def test_yearly_alias(self):
        assert PropertyLedgerEntry.YEARLY == PropertyLedgerEntry.RecurrenceType.YEARLY

    def test_recurrence_type_choices(self):
        assert (
            PropertyLedgerEntry.RECURRENCE_TYPE_CHOICES
            == PropertyLedgerEntry.RecurrenceType.choices
        )


@pytest.mark.django_db
class TestPropertyLedgerEntryWithLease:
    def test_entry_can_have_lease(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            last_name="Dupont",
            start_date=datetime.date(2022, 1, 1),
            rent_amount=Money(Decimal("800.00"), "EUR"),
        )
        entry = PropertyLedgerEntry.objects.create(
            property=property_obj,
            lease=lease,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("800.00"), "EUR"),
            entry_date=datetime.date(2023, 1, 1),
        )
        assert entry.lease == lease

    def test_entry_without_lease(self, income_entry):
        assert income_entry.lease is None
