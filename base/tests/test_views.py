"""Test base views."""

import pytest
from django.urls import reverse

from tests.conftest import ADMIN_USER


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("index")
    response = client.get(path)
    assert response.url == "/accounts/login/?next=/"
    assert response.status_code == 302


@pytest.mark.django_db
def test_index_view_authenticated(admin_client):
    """Test that authenticated users who can access the index page."""
    path = reverse("index")
    response = admin_client.get(path)
    assert response.status_code == 200
    assert f"Welcome to {ADMIN_USER}" in response.content.decode()
