"""Conf test file for setting up fixtures in Django tests."""

import pytest
from django.contrib.auth import get_user_model

from django.test import Client

User = get_user_model()


# Constants for test users
ADMIN_USER = "admin"
ADMIN_PASSWORD = "adminpassword"

TEST_USER = "testuser"
TEST_PASSWORD = "testpassword"


@pytest.fixture
def admin_user():
    """Fixture to create and return a superuser."""
    new_admin = User.objects.create_superuser(
        username=ADMIN_USER,
        email="admin@site.com",
        password=ADMIN_PASSWORD,
    )
    return new_admin


@pytest.fixture
def user():
    """Fixture to create and return a regular user."""
    new_user = User.objects.create_user(
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
