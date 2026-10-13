"""Check that the generated fixtures can be read back through the ORM."""

import datetime

import pytest
from django.apps import apps
from django.urls import reverse


@pytest.mark.django_db
def test_all_fixture_rows_are_readable():
    """Invalid values (e.g. a decimal exceeding max_digits) only fail when read back on SQLite."""
    for model in apps.get_models():
        list(model._default_manager.all())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "index",
        "property:checks",
        "allocation",
        "finance:other_asset_list",
        "budget:index",
    ],
)
def test_pages_render_with_fixtures(admin_client, url_name):
    """Pages that aggregate every property render on the full fixture data set."""
    response = admin_client.get(reverse(url_name))
    assert response.status_code == 200


@pytest.mark.django_db
def test_budget_renders_with_fixtures(admin_client):
    """The demo budget of this year, compared with last year, for one member."""
    year = datetime.date.today().year
    response = admin_client.get(reverse("budget:year", args=[year]), {"person": 101})
    assert response.status_code == 200
    assert response.context["summary"].has_previous
    assert response.context["indicators"].income > 0
