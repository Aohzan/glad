"""Conftest file for property app tests."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import PropertyLoan
from tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USER,
    TEST_PASSWORD,
    TEST_USER,
    admin_client,
    admin_user,
    client,
    user,
    user_client,
)


@pytest.fixture
def loan(property_obj):
    return PropertyLoan.objects.create(
        property=property_obj,
        name="Test Loan",
        lender="Test Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200000, "EUR"),
        monthly_payment=Money(900, "EUR"),
        interest_rate=Decimal("1.5"),
        insurance_rate=Decimal("0.2"),
    )


__all__ = [
    "ADMIN_USER",
    "ADMIN_PASSWORD",
    "TEST_USER",
    "TEST_PASSWORD",
    "admin_user",
    "user",
    "client",
    "admin_client",
    "user_client",
    "loan",
]
