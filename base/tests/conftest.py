"""
Conftest file for base app tests.
This file imports fixtures from the central conftest.py
to make them available to tests in this directory.
"""

# Import finance fixtures to make them available
from finance.tests.conftest import (  # noqa: F401
    declining_saving_account,
    saving_account_type,
)
