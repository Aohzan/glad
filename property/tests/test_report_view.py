"""Tests for the income & expenses report view and service."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLedgerEntry
from property.services.report import get_income_expense_report

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_property(name="Test Prop"):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )


def _make_entry(prop, flow_type, category, amount, date):
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=flow_type,
        management_category=category,
        amount=Money(amount, "EUR"),
        entry_date=date,
        description="test",
    )


def _make_recurring_entry(
    prop,
    flow_type,
    category,
    amount,
    start_date,
    recurrence_type,
    recurrence_end_date=None,
):
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=flow_type,
        management_category=category,
        amount=Money(amount, "EUR"),
        entry_date=start_date,
        recurrence_type=recurrence_type,
        recurrence_end_date=recurrence_end_date,
        description="recurring test",
    )


# ─── Service tests ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetIncomeExpenseReport:
    def setup_method(self):
        self.prop = _make_property()
        self.income_entry = _make_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("1000"),
            datetime.date(2025, 3, 1),
        )
        self.expense_entry = _make_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.EXPENSE,
            PropertyLedgerEntry.ManagementCategory.INSURANCE,
            Decimal("150"),
            datetime.date(2025, 3, 15),
        )

    def test_totals(self):
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        assert result["total_income"] == Decimal("1000")
        assert result["total_expenses"] == Decimal("150")
        assert result["net"] == Decimal("850")

    def test_category_breakdown(self):
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        categories = {r["category"]: r for r in result["by_category"]}
        assert "rent_collected" in categories
        assert categories["rent_collected"]["total"] == Decimal("1000")
        assert categories["rent_collected"]["flow_type"] == "income"
        assert "insurance" in categories
        assert categories["insurance"]["total"] == Decimal("150")
        assert categories["insurance"]["flow_type"] == "expense"

    def test_empty_result_when_no_entries_in_period(self):
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2024, 1, 1),
            datetime.date(2024, 12, 31),
        )
        assert result["total_income"] == Decimal("0")
        assert result["total_expenses"] == Decimal("0")
        assert result["net"] == Decimal("0")
        assert result["by_category"] == []

    def test_date_range_filter_start_date(self):
        # Entry before start_date should be excluded
        _make_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.OTHER_INCOME,
            Decimal("500"),
            datetime.date(2025, 1, 1),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 2, 1),
            datetime.date(2025, 12, 31),
        )
        # Only the March entry should be included (500 from Jan excluded)
        assert result["total_income"] == Decimal("1000")

    def test_date_range_filter_end_date(self):
        # Entry after end_date should be excluded
        _make_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.OTHER_INCOME,
            Decimal("500"),
            datetime.date(2025, 12, 31),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 6, 30),
        )
        assert result["total_income"] == Decimal("1000")

    def test_multiple_properties(self):
        prop2 = _make_property(name="Prop 2")
        _make_entry(
            prop2,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("800"),
            datetime.date(2025, 4, 1),
        )
        result = get_income_expense_report(
            [self.prop.pk, prop2.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        assert result["total_income"] == Decimal("1800")

    def test_no_date_filter(self):
        result = get_income_expense_report([self.prop.pk], None, None)
        assert result["total_income"] == Decimal("1000")
        assert result["total_expenses"] == Decimal("150")

    def test_entries_queryset_ordered_by_date(self):
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        dates = [e.entry_date for e in result["entries"]]
        assert dates == sorted(dates)

    def test_recurring_monthly_started_before_range(self):
        # Monthly entry started in 2024 should produce 12 occurrences in 2025
        _make_recurring_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("500"),
            start_date=datetime.date(2024, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2026, 12, 31),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        # 12 monthly occurrences × 500 + 1000 non-recurring = 7000
        assert result["total_income"] == Decimal("7000")

    def test_recurring_monthly_started_within_range(self):
        # Monthly entry started in March 2025 → 10 occurrences (Mar–Dec)
        _make_recurring_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.EXPENSE,
            PropertyLedgerEntry.ManagementCategory.INSURANCE,
            Decimal("100"),
            start_date=datetime.date(2025, 3, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2025, 12, 31),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        # 10 occurrences × 100 + 150 non-recurring = 1150
        assert result["total_expenses"] == Decimal("1150")

    def test_recurring_entry_with_end_date_before_range_excluded(self):
        # Recurring entry that ended before the range starts — no occurrences
        _make_recurring_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.OTHER_INCOME,
            Decimal("200"),
            start_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2024, 12, 31),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        # Only the existing non-recurring income entry (1000) should count
        assert result["total_income"] == Decimal("1000")

    def test_recurring_yearly_counted_once_per_year(self):
        # Yearly entry started in 2020 → 1 occurrence in 2025
        _make_recurring_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.EXPENSE,
            PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
            Decimal("800"),
            start_date=datetime.date(2020, 6, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        # 1 occurrence × 800 + 150 non-recurring = 950
        assert result["total_expenses"] == Decimal("950")

    def test_recurring_occurrences_in_entries_list(self):
        # Entries list should contain individual occurrences sorted by date
        _make_recurring_entry(
            self.prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("500"),
            start_date=datetime.date(2025, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2025, 3, 31),
        )
        result = get_income_expense_report(
            [self.prop.pk],
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
        )
        dates = [e.entry_date for e in result["entries"]]
        assert dates == sorted(dates)
        # 3 recurring occurrences (Jan, Feb, Mar) + 2 non-recurring = 5 entries
        assert len(dates) == 5


# ─── View tests ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestReportView:
    def test_get_no_filters_returns_200(self, user_client):
        response = user_client.get(reverse("property:report"))
        assert response.status_code == 200
        assert b"Income" in response.content or b"Rapport" in response.content

    def test_get_with_filters_shows_report(self, user_client):
        prop = _make_property()
        _make_entry(
            prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("1200"),
            datetime.date(2025, 5, 1),
        )
        response = user_client.get(
            reverse("property:report"),
            {"start_date": "2025-01-01", "end_date": "2025-12-31"},
        )
        assert response.status_code == 200
        assert response.context["report"] is not None
        assert response.context["report"]["total_income"] == Decimal("1200")

    def test_get_filter_by_specific_property(self, user_client):
        prop1 = _make_property("Prop A")
        prop2 = _make_property("Prop B")
        _make_entry(
            prop1,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("900"),
            datetime.date(2025, 5, 1),
        )
        _make_entry(
            prop2,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("600"),
            datetime.date(2025, 5, 1),
        )
        response = user_client.get(
            reverse("property:report"),
            {
                "properties": [prop1.pk],
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            },
        )
        assert response.status_code == 200
        assert response.context["report"]["total_income"] == Decimal("900")

    def test_get_empty_period_shows_no_entries_message(self, user_client):
        response = user_client.get(
            reverse("property:report"),
            {"start_date": "2000-01-01", "end_date": "2000-12-31"},
        )
        assert response.status_code == 200
        # report should have zero totals
        assert response.context["report"]["total_income"] == Decimal("0")
        assert response.context["report"]["total_expenses"] == Decimal("0")

    def test_csv_export(self, user_client):
        prop = _make_property()
        _make_entry(
            prop,
            PropertyLedgerEntry.FlowType.INCOME,
            PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            Decimal("750"),
            datetime.date(2025, 6, 1),
        )
        response = user_client.get(
            reverse("property:report"),
            {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "format": "csv",
            },
        )
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "attachment" in response["Content-Disposition"]
        content = response.content.decode("utf-8")
        assert (
            "date,property,flow_type,management_category,amount,description" in content
        )
        assert "750" in content

    def test_csv_export_includes_correct_fields(self, user_client):
        prop = _make_property("My House")
        _make_entry(
            prop,
            PropertyLedgerEntry.FlowType.EXPENSE,
            PropertyLedgerEntry.ManagementCategory.INSURANCE,
            Decimal("200"),
            datetime.date(2025, 7, 15),
        )
        response = user_client.get(
            reverse("property:report"),
            {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "format": "csv",
            },
        )
        content = response.content.decode("utf-8")
        assert "2025-07-15" in content
        assert "My House" in content
        assert "expense" in content
        assert "insurance" in content
        assert "200" in content

    def test_redirect_unauthenticated(self, client):
        response = client.get(reverse("property:report"))
        assert response.status_code == 302
        assert (
            "/accounts/login/" in response["Location"]
            or "login" in response["Location"]
        )
