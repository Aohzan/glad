"""
Root conftest.py - makes shared fixtures available to all test directories.

Fixtures and constants defined in tests/conftest.py are re-exported here so
pytest's directory-based discovery propagates them automatically, removing the
need for each sub-app conftest to import them explicitly.
"""

from tests.conftest import (  # noqa: F401
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
