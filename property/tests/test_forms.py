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
    # 200 000 at 3.5 % over 240 months: the annuity is 1159.92
    assert cd["monthly_payment"] == Money(Decimal("1159.92"), "EUR")
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
    assert loan.monthly_payment == Money(Decimal("1159.92"), "EUR")
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
    # interest_rate is optional (smoothed loans / prêts lisseurs don't need it)
    assert "interest_rate" not in form.errors


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


@pytest.mark.django_db
def test_loan_form_empty_interest_rate_saves_zero(prop):
    """An empty interest rate is saved as 0 instead of failing on NOT NULL."""
    form = PropertyLoanForm(
        data=_base_data(
            interest_rate="", duration_months="24", original_amount_0="24000"
        )
    )
    assert form.is_valid(), form.errors

    form.instance.property = prop
    loan = form.save()

    loan.refresh_from_db()
    assert loan.interest_rate == Decimal(0)
    assert loan.insurance_rate == Decimal(0)
    assert loan.monthly_payment == Money(Decimal("1000.00"), "EUR")


@pytest.mark.django_db
def test_loan_form_rejects_first_payment_before_start(prop):
    """The first payment must come after the disbursement."""
    for first_payment_date in ("2023-12-01", "2024-01-01"):
        form = PropertyLoanForm(data=_base_data(first_payment_date=first_payment_date))
        assert not form.is_valid()
        assert "first_payment_date" in form.errors


def _existing_loan(prop, **overrides) -> PropertyLoan:
    """A saved loan whose amounts were set by hand, not by the form."""
    fields = {
        "property": prop,
        "name": "Main Loan",
        "lender": "BNP",
        "start_date": datetime.date(2024, 1, 1),
        "end_date": datetime.date(2044, 1, 1),
        "original_amount": Money(200000, "EUR"),
        "interest_rate": Decimal("3.50"),
        "insurance_rate": Decimal("0.36"),
        "monthly_payment": Money(Decimal("1170.00"), "EUR"),
        "insurance": Money(Decimal("55.00"), "EUR"),
    }
    fields.update(overrides)
    return PropertyLoan.objects.create(**fields)


@pytest.mark.django_db
def test_loan_form_rename_keeps_stored_amounts(prop):
    """Editing a field that does not drive the amounts keeps them as stored."""
    loan = _existing_loan(prop)
    form = PropertyLoanForm(
        data=_base_data(name="Renamed", insurance_rate="0.36"), instance=loan
    )
    assert form.is_valid(), form.errors
    form.save()

    loan.refresh_from_db()
    assert loan.name == "Renamed"
    assert loan.monthly_payment == Money(Decimal("1170.00"), "EUR")
    assert loan.insurance == Money(Decimal("55.00"), "EUR")


@pytest.mark.django_db
def test_loan_form_recomputes_the_amounts_whose_inputs_changed(prop):
    """A new rate recomputes the payment; a cleared insurance rate drops it."""
    loan = _existing_loan(prop)
    form = PropertyLoanForm(
        data=_base_data(interest_rate="3.00", insurance_rate="0.36"), instance=loan
    )
    assert form.is_valid(), form.errors
    form.save()
    loan.refresh_from_db()
    assert loan.monthly_payment == Money(Decimal("1109.20"), "EUR")
    assert loan.insurance == Money(Decimal("55.00"), "EUR")

    form = PropertyLoanForm(data=_base_data(interest_rate="3.00"), instance=loan)
    assert form.is_valid(), form.errors
    form.save()
    loan.refresh_from_db()
    assert loan.monthly_payment == Money(Decimal("1109.20"), "EUR")
    assert loan.insurance is None


@pytest.mark.django_db
def test_loan_form_computes_a_missing_payment(prop):
    """A loan saved without a payment gets one even if nothing changed."""
    loan = _existing_loan(prop, monthly_payment=None)
    form = PropertyLoanForm(data=_base_data(insurance_rate="0.36"), instance=loan)
    assert form.is_valid(), form.errors
    form.save()

    loan.refresh_from_db()
    assert loan.monthly_payment == Money(Decimal("1159.92"), "EUR")
