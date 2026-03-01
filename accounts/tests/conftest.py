"""
Conftest file for accounts app tests.
Imports shared fixtures from the central conftest.py.
"""

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
]
