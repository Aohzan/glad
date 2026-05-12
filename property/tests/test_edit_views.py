"""Tests for property/views/edit_views.py."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLoan


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Edit Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def loan(property_obj):
    return PropertyLoan.objects.create(
        property=property_obj,
        name="Test Loan",
        lender="Test Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(150000, "EUR"),
        monthly_payment=Money(700, "EUR"),
        interest_rate=Decimal("1.5"),
    )


@pytest.mark.django_db
class TestEditProperty:
    def test_get_edit_property(self, user_client, property_obj):
        url = reverse("property:edit", kwargs={"pk": property_obj.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert "property_form" in response.context

    def test_post_edit_property_valid(self, user_client, property_obj):
        url = reverse("property:edit", kwargs={"pk": property_obj.pk})
        data = {
            "name": "Updated Property Name",
            "property_type": Property.APARTMENT,
            "buying_value_0": "200000",
            "buying_value_1": "EUR",
            "buying_date": "2020-01-01",
            "is_active": "on",
            "tax_regime": "none",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        property_obj.refresh_from_db()
        assert property_obj.name == "Updated Property Name"
        messages = list(get_messages(response.wsgi_request))
        assert any("updated" in str(m).lower() for m in messages)

    def test_post_edit_property_invalid(self, user_client, property_obj):
        url = reverse("property:edit", kwargs={"pk": property_obj.pk})
        data = {
            "name": "",  # Required field
            "property_type": Property.APARTMENT,
            "buying_value_0": "200000",
            "buying_value_1": "EUR",
            "buying_date": "2020-01-01",
        }
        response = user_client.post(url, data)
        assert response.status_code == 200
        messages = list(get_messages(response.wsgi_request))
        assert any(
            "error" in str(m).lower() or "correct" in str(m).lower() for m in messages
        )

    def test_edit_property_404_for_nonexistent(self, user_client):
        url = reverse("property:edit", kwargs={"pk": 99999})
        response = user_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestCreateProperty:
    def test_get_create_property(self, user_client):
        url = reverse("property:create")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "property_form" in response.context

    def test_post_create_property_valid(self, user_client):
        url = reverse("property:create")
        data = {
            "name": "New Property",
            "property_type": Property.HOUSE,
            "buying_value_0": "300000",
            "buying_value_1": "EUR",
            "buying_date": "2023-01-01",
            "is_active": "on",
            "tax_regime": "none",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert Property.objects.filter(name="New Property").exists()
        messages = list(get_messages(response.wsgi_request))
        assert any("created" in str(m).lower() for m in messages)

    def test_post_create_property_invalid(self, user_client):
        url = reverse("property:create")
        data = {
            "name": "",  # Required
            "property_type": Property.HOUSE,
            "buying_value_0": "300000",
            "buying_value_1": "EUR",
            "buying_date": "2023-01-01",
        }
        response = user_client.post(url, data)
        assert response.status_code == 200
        messages = list(get_messages(response.wsgi_request))
        assert any(
            "error" in str(m).lower() or "correct" in str(m).lower() for m in messages
        )


@pytest.mark.django_db
class TestManagePropertyLoans:
    def test_get_redirects_to_detail(self, user_client, property_obj):
        url = reverse("property:loans", kwargs={"pk": property_obj.pk})
        response = user_client.get(url)
        assert response.status_code == 302
        assert f"/property/{property_obj.pk}" in response["Location"]

    def test_post_manage_loans_invalid_redirects_with_error(
        self, user_client, property_obj
    ):
        url = reverse("property:loans", kwargs={"pk": property_obj.pk})
        # Post with empty/invalid formset data
        data = {
            "loans-TOTAL_FORMS": "1",
            "loans-INITIAL_FORMS": "0",
            "loans-MIN_NUM_FORMS": "0",
            "loans-MAX_NUM_FORMS": "1000",
            "loans-0-name": "",
            "loans-0-start_date": "invalid-date",
            "loans-0-end_date": "2040-01-01",
            "loans-0-original_amount_0": "150000",
            "loans-0-original_amount_1": "EUR",
            "loans-0-interest_rate": "1.5",
            "loans-0-insurance_rate": "0.0",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302

    def test_post_manage_loans_404_for_nonexistent(self, user_client):
        url = reverse("property:loans", kwargs={"pk": 99999})
        response = user_client.post(
            url,
            {
                "loans-TOTAL_FORMS": "0",
                "loans-INITIAL_FORMS": "0",
                "loans-MIN_NUM_FORMS": "0",
                "loans-MAX_NUM_FORMS": "1000",
            },
        )
        assert response.status_code == 404

    def test_post_manage_loans_valid_saves_and_redirects(
        self, user_client, property_obj
    ):
        url = reverse("property:loans", kwargs={"pk": property_obj.pk})
        data = {
            "loans-TOTAL_FORMS": "1",
            "loans-INITIAL_FORMS": "0",
            "loans-MIN_NUM_FORMS": "0",
            "loans-MAX_NUM_FORMS": "1000",
            "loans-0-name": "New Loan",
            "loans-0-lender": "Bank",
            "loans-0-start_date": "2023-01-01",
            "loans-0-duration_months": "240",
            "loans-0-original_amount_0": "150000",
            "loans-0-original_amount_1": "EUR",
            "loans-0-interest_rate": "1.5",
            "loans-0-insurance_rate": "0.0",
            "loans-0-DELETE": "",
            # Schedule formset for the new loan (form index 0)
            "schedules_new_0-TOTAL_FORMS": "0",
            "schedules_new_0-INITIAL_FORMS": "0",
            "schedules_new_0-MIN_NUM_FORMS": "0",
            "schedules_new_0-MAX_NUM_FORMS": "1000",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert PropertyLoan.objects.filter(
            property=property_obj, name="New Loan"
        ).exists()


@pytest.mark.django_db
class TestGenerateLoanAmortization:
    """Tests for the generate_loan_amortization view."""

    def test_generate_with_stored_monthly_payment(self, user_client, loan):
        """Generate should succeed when monthly_payment is already stored."""
        url = reverse(
            "property:loan_amortization_generate",
            kwargs={"pk": loan.property.pk, "loan_pk": loan.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        from property.models import PropertyLoanAmortizationEntry

        assert PropertyLoanAmortizationEntry.objects.filter(loan=loan).exists()
        messages = list(get_messages(response.wsgi_request))
        assert any(
            "generated" in str(m).lower() or "entries" in str(m).lower()
            for m in messages
        )

    def test_generate_without_monthly_payment_computes_from_params(
        self, user_client, property_obj
    ):
        """Generate should compute monthly_payment from loan params when not stored."""
        loan_no_payment = PropertyLoan.objects.create(
            property=property_obj,
            name="Loan No Payment",
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(150000, "EUR"),
            monthly_payment=None,
            monthly_payment_currency="EUR",
            interest_rate=Decimal("1.5"),
        )
        url = reverse(
            "property:loan_amortization_generate",
            kwargs={"pk": property_obj.pk, "loan_pk": loan_no_payment.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        from property.models import PropertyLoanAmortizationEntry

        assert PropertyLoanAmortizationEntry.objects.filter(
            loan=loan_no_payment
        ).exists()

    def test_generate_without_monthly_payment_and_no_rate_shows_error(
        self, user_client, property_obj
    ):
        """Generate should show error when monthly_payment cannot be computed (zero duration)."""
        loan_no_rate = PropertyLoan.objects.create(
            property=property_obj,
            name="Loan No Rate",
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 1, 1),  # same start/end → duration=0
            original_amount=Money(150000, "EUR"),
            monthly_payment=None,
            monthly_payment_currency="EUR",
            interest_rate=Decimal("1.5"),
        )
        url = reverse(
            "property:loan_amortization_generate",
            kwargs={"pk": property_obj.pk, "loan_pk": loan_no_rate.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        messages = list(get_messages(response.wsgi_request))
        assert any("monthly payment" in str(m).lower() for m in messages)
