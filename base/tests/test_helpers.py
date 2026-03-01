"""Tests for base view helper functions."""

import datetime

from django.test import RequestFactory

from base.views import healthcheck, safe_date_compare


def test_safe_date_compare_handles_mixed_date_types():
    date_value = datetime.date(2025, 1, 2)
    dt_value = datetime.datetime(2025, 1, 3, 10, 0, 0)

    assert safe_date_compare(date_value, dt_value) is True
    assert safe_date_compare(dt_value, date_value) is False
    assert safe_date_compare(date_value, date_value) is True


def test_healthcheck_view_returns_ok_json():
    request = RequestFactory().get("/health")
    response = healthcheck(request)
    assert response.status_code == 200
    assert response.content.decode("utf-8") == '{"status": "OK"}'
