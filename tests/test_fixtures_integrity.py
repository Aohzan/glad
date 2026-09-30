"""Check that the generated fixtures can be read back through the ORM."""

import pytest
from django.apps import apps
from django.urls import reverse


@pytest.mark.django_db
def test_all_fixture_rows_are_readable():
    """Invalid values (e.g. a decimal exceeding max_digits) only fail when read back on SQLite."""
    for model in apps.get_models():
        list(model._default_manager.all())


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["index", "property:checks"])
def test_pages_render_with_fixtures(admin_client, url_name):
    """Pages that aggregate every property render on the full fixture data set."""
    response = admin_client.get(reverse(url_name))
    assert response.status_code == 200
