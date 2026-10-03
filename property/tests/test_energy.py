"""Tests for the DPE rental ban and validity rules."""

import datetime

import pytest
from django.urls import reverse

from property.services.energy import (
    dpe_expiry,
    get_dpe_status,
    rent_increase_allowed,
)

TODAY = datetime.date(2026, 10, 1)


class TestDpeExpiry:
    @pytest.mark.parametrize(
        ("made_on", "expires_on"),
        [
            (datetime.date(2016, 5, 1), datetime.date(2022, 12, 31)),
            (datetime.date(2019, 5, 1), datetime.date(2024, 12, 31)),
            (datetime.date(2021, 7, 1), datetime.date(2031, 6, 30)),
        ],
    )
    def test_expiry(self, made_on, expires_on):
        assert dpe_expiry(made_on) == expires_on


class TestDpeStatus:
    def test_no_rating(self):
        assert get_dpe_status("", datetime.date(2024, 1, 1)) is None

    def test_g_is_banned(self):
        status = get_dpe_status("G", None, today=TODAY)
        assert status is not None
        assert status.is_banned is True
        assert status.rent_frozen is True
        assert status.expires_on is None
        assert status.level == "danger"

    def test_f_ban_is_near(self):
        status = get_dpe_status("F", datetime.date(2024, 1, 1), today=TODAY)
        assert status is not None
        assert status.is_banned is False
        assert status.ban_is_near is True
        assert status.level == "warning"

    def test_e_ban_is_far(self):
        status = get_dpe_status("E", datetime.date(2024, 1, 1), today=TODAY)
        assert status is not None
        assert status.ban_date == datetime.date(2034, 1, 1)
        assert status.ban_is_near is False
        assert status.level is None

    def test_expired_dpe(self):
        status = get_dpe_status("C", datetime.date(2019, 1, 1), today=TODAY)
        assert status is not None
        assert status.is_expired is True
        assert status.level == "danger"

    def test_expires_soon(self):
        status = get_dpe_status("B", datetime.date(2021, 12, 1), today=TODAY)
        assert status is not None
        assert status.expires_soon is False
        soon = get_dpe_status(
            "B", datetime.date(2021, 7, 1), today=datetime.date(2031, 3, 1)
        )
        assert soon is not None
        assert soon.expires_soon is True
        assert soon.level == "warning"

    def test_rent_increase_allowed(self):
        assert rent_increase_allowed("E") is True
        assert rent_increase_allowed("F") is False


@pytest.mark.django_db
class TestDpeDisplay:
    def test_detail_shows_rating_and_ban(self, user_client, make_property):
        prop = make_property("Old flat")
        prop.dpe_rating = "G"
        prop.dpe_date = datetime.date(2022, 3, 1)
        prop.save()
        response = user_client.get(reverse("property:panel_info", args=[prop.pk]))
        content = response.content.decode()
        assert 'id="dpe-status"' in content
        assert "dpe-g" in content
        assert "cannot be rented out as a main residence since" in content
        assert "The rent cannot be increased" in content

    def test_detail_without_rating(self, user_client, make_property):
        prop = make_property("New flat")
        response = user_client.get(reverse("property:panel_info", args=[prop.pk]))
        assert 'id="dpe-status"' not in response.content.decode()

    def test_model_status(self, make_property):
        prop = make_property("Flat")
        assert prop.dpe_status is None
        prop.dpe_rating = "D"
        prop.save()
        prop.refresh_from_db()
        assert prop.dpe_status is not None
        assert prop.dpe_status.level is None
