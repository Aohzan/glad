"""Tests for property forms, focusing on PropertyLoanForm."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.forms import PropertyLoanForm
from property.models import Property, PropertyLoan


@pytest.fixture
def prop(db):
    return Property.objects.create(
        name="Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


def _base_data(**overrides):
    """Return minimal valid form data for PropertyLoanForm."""
    data = {
        "name": "Main Loan",
        "lender": "BNP",
        "start_date": "2024-01-01",
        "duration_months": "240",
        "original_amount_0": "200000",
        "original_amount_1": "EUR",
        "interest_rate": "3.50",
        "insurance_rate": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_loan_form_valid_computes_end_date_and_monthly_payment(prop):
    """Valid form should compute end_date and monthly_payment automatically."""
    data = _base_data()
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    cd = form.cleaned_data
    # end_date = start_date + 240 months = 2044-01-01
    assert cd["end_date"] == datetime.date(2044, 1, 1)
    # monthly_payment should be ~1159.97
    assert cd["monthly_payment"] is not None
    assert abs(float(cd["monthly_payment"].amount) - 1159.97) < 1.0
    # No insurance rate → insurance is None
    assert cd["insurance"] is None


@pytest.mark.django_db
def test_loan_form_with_insurance_rate(prop):
    """Form with insurance_rate should compute insurance amount."""
    data = _base_data(insurance_rate="0.36")
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    cd = form.cleaned_data
    # Insurance: 200000 * 0.36% / 12 = 60
    assert cd["insurance"] is not None
    assert abs(float(cd["insurance"].amount) - 60.0) < 0.5


@pytest.mark.django_db
def test_loan_form_save_sets_end_date_and_monthly_payment(prop):
    """Saving the form should persist computed end_date and monthly_payment."""
    data = _base_data(insurance_rate="0.36")
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    instance = form.save(commit=False)
    instance.property = prop
    instance.save()

    loan = PropertyLoan.objects.get(pk=instance.pk)
    assert loan.end_date == datetime.date(2044, 1, 1)
    assert loan.monthly_payment is not None
    assert abs(float(loan.monthly_payment.amount) - 1159.97) < 1.0
    assert loan.insurance is not None
    assert abs(float(loan.insurance.amount) - 60.0) < 0.5


@pytest.mark.django_db
def test_loan_form_save_without_insurance(prop):
    """Saving without insurance_rate should leave insurance as None."""
    data = _base_data()
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    instance = form.save(commit=False)
    instance.property = prop
    instance.save()

    loan = PropertyLoan.objects.get(pk=instance.pk)
    assert loan.insurance is None


@pytest.mark.django_db
def test_loan_form_prefills_duration_from_existing_instance(prop):
    """Editing an existing loan should pre-fill duration_months."""
    loan = PropertyLoan.objects.create(
        property=prop,
        name="Existing Loan",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2044, 1, 1),
        original_amount=Money(150000, "EUR"),
        interest_rate=Decimal("2.5"),
    )
    form = PropertyLoanForm(instance=loan)
    assert form.fields["duration_months"].initial == 240


@pytest.mark.django_db
def test_loan_form_invalid_missing_required_fields():
    """Form should be invalid when required fields are missing."""
    form = PropertyLoanForm(data={})
    assert not form.is_valid()
    assert "start_date" in form.errors
    assert "duration_months" in form.errors
    assert "original_amount" in form.errors
    # interest_rate is required in the form (needed to compute monthly payment)
    assert "interest_rate" in form.errors


@pytest.mark.django_db
def test_loan_form_invalid_duration_too_low():
    """Duration of 0 should fail min_value validation."""
    data = _base_data(duration_months="0")
    form = PropertyLoanForm(data=data)
    assert not form.is_valid()
    assert "duration_months" in form.errors


@pytest.mark.django_db
def test_loan_form_zero_interest_rate(prop):
    """Zero interest rate should still compute a valid monthly payment."""
    data = _base_data(
        interest_rate="0", duration_months="24", original_amount_0="24000"
    )
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    cd = form.cleaned_data
    assert abs(float(cd["monthly_payment"].amount) - 1000.0) < 0.01


@pytest.mark.django_db
def test_loan_form_save_with_commit_true(prop):
    """save(commit=True) should persist the instance directly."""
    data = _base_data()
    form = PropertyLoanForm(data=data)
    assert form.is_valid(), form.errors

    # Inject property via instance before save
    form.instance.property = prop
    instance = form.save(commit=True)

    assert instance.pk is not None
    assert instance.end_date == datetime.date(2044, 1, 1)
    assert instance.monthly_payment is not None
