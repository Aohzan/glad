"""Tests for property/views/loans_views.py (all loans dashboard)."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyLoanAmortizationEntry


def _make_property(name="Test Prop"):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )


def _make_loan(prop, **kwargs):
    defaults = {
        "name": "Test Loan",
        "lender": "Test Bank",
        "start_date": datetime.date.today() - datetime.timedelta(days=365),
        "end_date": datetime.date.today() + datetime.timedelta(days=365 * 10),
        "original_amount": Money(150_000, "EUR"),
        "monthly_payment": Money(700, "EUR"),
        "interest_rate": Decimal("2.0"),
    }
    defaults.update(kwargs)
    return PropertyLoan.objects.create(property=prop, **defaults)


@pytest.mark.django_db
class TestAllLoansView:
    def test_get_no_loans_returns_200(self, user_client):
        response = user_client.get(reverse("property:all_loans"))
        assert response.status_code == 200
        assert response.context["loans_with_totals"] == []

    def test_get_with_loans_shows_context(self, user_client):
        prop = _make_property()
        _make_loan(prop)
        response = user_client.get(reverse("property:all_loans"))
        assert response.status_code == 200
        loans_with_totals = response.context["loans_with_totals"]
        assert len(loans_with_totals) == 1
        item = loans_with_totals[0]
        assert item.loan.property == prop
        assert item.duration_months > 0
        assert item.remaining_balance.amount > 0
        assert item.capital_paid.amount > 0
        assert item.interest_paid.amount > 0
        assert item.insurance_paid.amount == 0

    def test_get_aggregates_across_multiple_properties(self, user_client):
        prop1 = _make_property("Prop A")
        prop2 = _make_property("Prop B")
        _make_loan(prop1)
        _make_loan(prop2, name="Second Loan")
        response = user_client.get(reverse("property:all_loans"))
        assert response.status_code == 200
        assert len(response.context["loans_with_totals"]) == 2

    def test_summary_totals_computed(self, user_client):
        prop = _make_property()
        _make_loan(prop)
        response = user_client.get(reverse("property:all_loans"))
        summary = response.context["summary"]
        assert summary.total_mensuality == Money(700, "EUR")
        assert summary.total_remaining.amount > Decimal(0)

    def test_summary_includes_insurance_paid(self, user_client):
        prop = _make_property()
        _make_loan(
            prop,
            insurance_rate=Decimal("0.3"),
            insurance=Money(37, "EUR"),
        )
        response = user_client.get(reverse("property:all_loans"))
        summary = response.context["summary"]
        assert summary.total_insurance_paid.amount > Decimal(0)
        assert summary.total_mensuality == Money(737, "EUR")

    def test_chart_data_present(self, user_client):
        prop = _make_property()
        _make_loan(prop)
        response = user_client.get(reverse("property:all_loans"))
        assert response.context["loan_chart_data"]["currency"] == "EUR"
        # The data reaches the chart through json_script, not inline JavaScript.
        assert 'id="loan-chart-data"' in response.content.decode()

    def test_csv_export(self, user_client):
        prop = _make_property("My House")
        _make_loan(prop)
        response = user_client.get(reverse("property:all_loans"), {"format": "csv"})
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "attachment" in response["Content-Disposition"]
        content = response.content.decode("utf-8")
        assert "property,loan_name,lender" in content
        assert "capital_paid,interest_paid,insurance_paid" in content
        assert "My House" in content
        assert "Test Loan" in content

    def test_redirect_unauthenticated(self, client):
        response = client.get(reverse("property:all_loans"))
        assert response.status_code == 302
        assert (
            "/accounts/login/" in response["Location"]
            or "login" in response["Location"]
        )

    def test_loan_without_monthly_payment_is_repaid_by_the_annuity(self, user_client):
        """A loan saved without a monthly payment is repaid by its annuity."""
        prop = _make_property()
        _make_loan(prop, monthly_payment=None, interest_rate=Decimal("0.0"))
        response = user_client.get(reverse("property:all_loans"))
        item = response.context["loans_with_totals"][0]
        # 0 % and no insurance: the loan costs nothing.
        assert item.total_cost == Money(0, "EUR")
        assert item.total_repaid == Money(150_000, "EUR")

    def test_chart_uses_amortization_entries_when_present(self, user_client):
        """The chart should aggregate imported amortization entries for a loan."""
        prop = _make_property()
        loan = _make_loan(prop)
        day = datetime.date.today() - datetime.timedelta(days=30)
        PropertyLoanAmortizationEntry.objects.create(
            loan=loan,
            date=day,
            capital=Money(280, "EUR"),
            interest=Money(20, "EUR"),
            remaining_balance_amount=Money(149_720, "EUR"),
        )
        response = user_client.get(reverse("property:all_loans"))
        assert response.status_code == 200
        chart_data = response.context["loan_chart_data"]
        assert chart_data["loans"] == [
            {
                "name": "Test Prop — Test Loan",
                "data": [{"x": day.strftime("%Y-%m-01"), "y": 300.0}],
            }
        ]

    def test_chart_includes_a_loan_without_stored_payment(self, user_client):
        """A loan saved without a monthly payment is charted with its annuity."""
        prop = _make_property()
        _make_loan(prop, monthly_payment=None, interest_rate=Decimal("0.0"))
        response = user_client.get(reverse("property:all_loans"))
        chart_data = response.context["loan_chart_data"]
        assert len(chart_data["loans"]) == 1

    def test_summary_skips_mismatched_currency(self, user_client):
        """Loans in a different currency than the first one are excluded from totals."""
        prop = _make_property()
        _make_loan(prop, name="EUR Loan")
        _make_loan(
            prop,
            name="USD Loan",
            original_amount=Money(50_000, "USD"),
            monthly_payment=Money(400, "USD"),
        )
        response = user_client.get(reverse("property:all_loans"))
        assert response.status_code == 200
        # Both loans are listed, but the summary only aggregates one currency.
        assert len(response.context["loans_with_totals"]) == 2
        summary = response.context["summary"]
        assert str(summary.total_remaining.currency) in ("EUR", "USD")
