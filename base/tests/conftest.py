"""
Conftest file for base app tests.
This file imports fixtures from the central conftest.py
to make them available to tests in this directory.
"""

# Import finance fixtures to make them available
from finance.tests.conftest import investment_account_type, saving_account_type
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

# Re-export all fixtures from the central conftest.py
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
    "saving_account_type",
    "investment_account_type",
]
