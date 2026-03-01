"""Conf test file for setting up fixtures in Django tests."""

import glob
import os
from typing import cast

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import UserManager
from django.core.management import call_command
from django.test import Client

# Set SECRET_KEY for tests
settings.SECRET_KEY = "test"
settings.LANGUAGE_CODE = "en"
settings.STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

User = get_user_model()


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Load fixtures from tests/fixtures and finance/fixtures directories."""
    with django_db_blocker.unblock():
        # Load fixtures from tests/fixtures directory
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        fixture_files = glob.glob(os.path.join(fixtures_dir, "*.yaml"))
        for fixture_file in fixture_files:
            fixture_name = os.path.basename(fixture_file)
            call_command("loaddata", os.path.join("tests", "fixtures", fixture_name))

        # Load fixtures from finance/fixtures directory
        finance_fixtures_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "finance", "fixtures"
        )
        finance_fixture_files = glob.glob(os.path.join(finance_fixtures_dir, "*.yaml"))
        for fixture_file in finance_fixture_files:
            fixture_name = os.path.basename(fixture_file)
            call_command("loaddata", os.path.join("finance", "fixtures", fixture_name))


# Constants for test users
ADMIN_USER = "admin"
ADMIN_PASSWORD = "adminpassword"

TEST_USER = "testuser"
TEST_PASSWORD = "testpassword"


@pytest.fixture
def admin_user():
    """Fixture to create and return a superuser."""
    user_manager = cast(UserManager, User.objects)
    new_admin = user_manager.create_superuser(
        username=ADMIN_USER,
        email="admin@site.com",
        password=ADMIN_PASSWORD,
    )
    return new_admin


@pytest.fixture
def user():
    """Fixture to create and return a regular user."""
    user_manager = cast(UserManager, User.objects)
    new_user = user_manager.create_user(
        username=TEST_USER,
        email="user@site.com",
        password=TEST_PASSWORD,
    )
    return new_user


@pytest.fixture
def client():
    """Fixture to create and return a Django test client."""
    return Client()


@pytest.fixture
def admin_client(admin_user, client):
    """Fixture to create and return an authenticated admin client."""
    client.login(username=ADMIN_USER, password=ADMIN_PASSWORD)
    return client


@pytest.fixture
def user_client(user, client):
    """Fixture to create and return an authenticated user client."""
    client.login(username=TEST_USER, password=TEST_PASSWORD)
    return client
